"""Offline checks for content rotation, untrusted feeds and email delivery state."""
import copy
import json
import os
import shutil
import smtplib
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import newsletter as app


class ContentTests(unittest.TestCase):
    def test_forty_weeks_without_repeating_a_question(self):
        banks, history, seen = app.load_banks(), {}, set()
        self.assertTrue(all(len(b) >= 120 for b in banks.values()))
        per_edition = len(app.SECTIONS) * 3
        for week in range(40):
            day = date(2026, 11, 16) + timedelta(weeks=week)
            chosen = app.select_questions(banks, history, 3)
            ids = {q['ID'] for bank in chosen.values() for q in bank}
            self.assertEqual(len(ids), per_edition)
            self.assertFalse(ids & seen)
            seen.update(ids)
            app.record_usage(history, chosen, [], day)
        self.assertEqual(len(seen), per_edition * 40)

    def test_exhausted_bank_returns_oldest_questions_first(self):
        banks = {key: bank[:3] for key, bank in app.load_banks().items()}
        history = {}
        for i in range(3):
            chosen = app.select_questions(banks, history, 1)
            app.record_usage(history, chosen, [], date(2026, 11, 1) + timedelta(weeks=i))
        again = app.select_questions(banks, history, 1)
        self.assertEqual(again['irish'][0]['ID'], banks['irish'][0]['ID'])

    def test_iso_week_boundary(self):
        self.assertEqual(app.edition_id(date(2027, 1, 1)), '2026-W53')
        self.assertEqual(app.edition_id(date(2026, 11, 16)), app.edition_id(date(2026, 11, 22)))

    def test_damaged_bank_fails_with_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.txt'
            path.write_text('ID: bad\nTITLE: test\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'bad.txt'):
                app.load_bank(path)

    def test_duplicate_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.txt'
            q = app.load_banks()['irish'][0]
            block = '\n'.join(f'{k}: {v}' for k, v in q.items())
            path.write_text(block + '\n---\n' + block, encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                app.load_bank(path)

    def test_invalid_answer_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.txt'
            q = dict(app.load_banks()['music'][0], ANSWER='E')
            path.write_text('\n'.join(f'{k}: {v}' for k, v in q.items()), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'ANSWER'):
                app.load_bank(path)

    def test_render_escapes_content_and_keeps_questions_before_key(self):
        selected = app.select_questions(app.load_banks(), {}, 3)
        selected['irish'][0]['QUESTION'] = '<script>alert("bad")</script>'
        original = copy.deepcopy(selected)
        body, plain = app.render_email(date(2026, 11, 20), selected, [], 'Offline test', demo=True)
        self.assertNotIn('<script>', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertIn('lang="en"', body)
        self.assertLess(body.index(app.NEWS_TITLE + '</h2>'), body.index('KEY 01'))
        self.assertLess(len(body.encode()), 100_000)  # Stay below common Gmail clipping size.
        self.assertIn('ANSWER KEY', plain)
        self.assertEqual(selected, original)

    def test_fourth_answer_can_be_correct_and_options_must_be_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'four.txt'
            q = dict(app.load_banks()['music'][0], ANSWER='D')
            path.write_text('\n'.join(f'{k}: {v}' for k, v in q.items()), encoding='utf-8')
            self.assertEqual(app.load_bank(path)[0]['ANSWER'], 'D')
            q['D'] = q['A']
            path.write_text('\n'.join(f'{k}: {v}' for k, v in q.items()), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'distinct'):
                app.load_bank(path)

    def test_all_banks_have_four_options_and_unique_questions(self):
        questions = [q for bank in app.load_banks().values() for q in bank]
        self.assertEqual(len({q['QUESTION'] for q in questions}), len(questions))
        for q in questions:
            self.assertTrue(all(q[letter] for letter in 'ABCD'), q['ID'])
            self.assertEqual(len({q[letter].casefold() for letter in 'ABCD'}), 4, q['ID'])

    def test_answer_key_repeats_questions_and_omits_reading_links(self):
        selected = app.select_questions(app.load_banks(), {}, 3)
        body, plain = app.render_email(date(2026, 11, 20), selected, [], '')
        self.assertNotIn('Explore the topic', body)
        self.assertNotIn('Explore the topic', plain)
        key = plain.split('ANSWER KEY AND WORKED EXAMPLES', 1)[1]
        for bank in selected.values():
            for q in bank:
                self.assertEqual(body.count(app.esc(q['QUESTION'])), 2, q['ID'])
                self.assertIn(q['QUESTION'], key)
                self.assertIn(f"Answer: {q['ANSWER']}. {q[q['ANSWER']]}", key)
                self.assertNotIn(q['SOURCE'], body)
                self.assertNotIn(q['SOURCE'], plain)
                self.assertIn(f"D. {q['D']}", plain)

    def test_new_category_and_news_numbering_are_consistent(self):
        keys = [key for key, *_ in app.SECTIONS]
        self.assertEqual(keys[:2], ['neuropsychology', 'mental_health'])
        selected = app.select_questions(app.load_banks(), {}, 3)
        body, plain = app.render_email(date(2026, 11, 20), selected, [], '')
        self.assertIn('02. Mental health case files', plain)
        self.assertIn('07. ' + app.NEWS_TITLE, plain)
        for q in app.load_banks()['mental_health']:
            self.assertTrue(q['QUESTION'].startswith(('DSM-5-TR', 'ICD-11')), q['ID'])
        self.assertIn('18 questions', body)

    def test_default_editions_stay_within_email_size_budget(self):
        banks, history = app.load_banks(), {}
        for week in range(40):
            day = date(2026, 11, 16) + timedelta(weeks=week)
            chosen = app.select_questions(banks, history, 3)
            body, _ = app.render_email(day, chosen, [], '')
            self.assertLess(len(body.encode('utf-8')), 100_000, f'Week {week + 1}')
            app.record_usage(history, chosen, [], day)


class NewsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)
        self.config = app.news_config()

    def item(self, title, age=1, source='Outlet A', url='https://example.org/story'):
        return dict(title=title, url=url, source=source,
                    published=(self.now - timedelta(days=age)).isoformat(), kind='Reporting')

    def test_stale_future_and_shared_articles_are_excluded(self):
        shared = self.item('Housing story already shared')
        items = [shared, self.item('Old story', 8, url='https://example.org/old'),
                 self.item('Future story', -1, url='https://example.org/future')]
        history = {'news': {app.story_key(shared): '2026-11-19'}}
        self.assertEqual(app.rank_news(items, self.config, history, self.now), [])

    def test_tracking_urls_do_not_repeat(self):
        one = self.item('Housing story', url='https://example.org/story?utm_source=one')
        two = self.item('Housing story', url='https://example.org/story?utm_source=two')
        self.assertEqual(len(app.rank_news([one, two], self.config, {}, self.now)), 1)

    def test_unrelated_sport_does_not_fill_news_and_rent_does_not_match_parents(self):
        config = dict(self.config, priority_terms={'rent': 4}, require_priority_match=True)
        irrelevant = self.item('Parents discuss an international football result')
        relevant = self.item('Rent increases across the country', url='https://example.org/rents')
        ranked = app.rank_news([irrelevant, relevant], config, {}, self.now)
        self.assertEqual([s['url'] for s in ranked], [relevant['url']])

    def test_near_duplicate_headlines_are_grouped(self):
        one = self.item('Housing rents rise sharply across Dublin this winter')
        two = self.item('Housing rents rise sharply across Dublin this winter, report finds',
                        source='Outlet B', url='https://example.net/another')
        self.assertEqual(len(app.rank_news([one, two], self.config, {}, self.now)), 1)

    def test_maximum_two_per_source(self):
        items = [self.item(title, url=f'https://example.org/{i}') for i, title in enumerate([
            'Housing construction programme', 'Hospital emergency capacity', 'Workers union pay dispute', 'Climate carbon policy'])]
        config = dict(self.config, relax_source_limit=False)
        self.assertEqual(len(app.rank_news(items, config, {}, self.now)), 2)

    def test_five_verified_stories_when_one_feed_is_unavailable(self):
        items = [self.item(title, source='Outlet A' if i < 3 else 'Outlet B', url=f'https://example.org/{i}')
                 for i, title in enumerate(['Vivienda y alquileres', 'Tribunal revisa un caso', 'Sanidad y hospitales',
                                            'Elecciones y programas', 'Educacion y escuelas'])]
        ranked = app.rank_news(items, dict(self.config, relax_source_limit=True), {}, self.now)
        self.assertEqual(len(ranked), 5)
        self.assertEqual(len({app.story_key(item) for item in ranked}), 5)

    def test_feed_dates_and_markup_are_checked(self):
        xml = b'''<rss><channel><item><title>&lt;b&gt;Housing update&lt;/b&gt;</title>
        <link>https://example.org/new</link><pubDate>Thu, 19 Nov 2026 10:00:00 GMT</pubDate></item>
        <item><title>Undated</title><link>https://example.org/unknown</link></item>
        <item><title>Old</title><link>https://example.org/old</link><pubDate>Thu, 01 Jan 2026 10:00:00 GMT</pubDate></item>
        </channel></rss>'''
        response = MagicMock()
        response.__enter__.return_value.read.return_value = xml
        with patch.object(app.urllib.request, 'urlopen', return_value=response):
            items = app.fetch_feed({'url': 'https://example.org/rss', 'name': 'Test'}, self.now, 7)
        self.assertEqual([i['title'] for i in items], ['Housing update'])

    def test_all_feed_failures_have_an_honest_notice(self):
        with patch.object(app, 'fetch_feed', side_effect=OSError('unavailable')):
            items, note = app.collect_news(self.now, {})
        self.assertEqual(items, [])
        self.assertIn('No se han podido consultar', note)

    def test_spanish_headlines_group_across_accents_and_common_articles(self):
        self.assertEqual(app.normal_title('El alquiler y la educación'), app.normal_title('Alquiler educacion'))

    def test_cross_source_coverage_outweighs_an_unrelated_single_source_story(self):
        shared = self.item('El Congreso aprueba nuevas medidas sobre vivienda', source='Outlet A')
        second = self.item('Congreso aprueba nuevas medidas sobre vivienda', source='Outlet B', url='https://other.example/measure')
        one_source = self.item('Emergencia en una localidad', source='Outlet C', url='https://third.example/event')
        ranked = app.rank_news([one_source, shared, second], self.config, {}, self.now)
        self.assertEqual(ranked[0]['coverage'], 2)

    def test_feed_section_filter_rejects_articles_outside_spain_section(self):
        xml = b'''<rss><channel>
        <item><title>National event</title><link>https://example.org/espana/event</link><pubDate>Thu, 19 Nov 2026 10:00:00 GMT</pubDate></item>
        <item><title>Foreign event</title><link>https://example.org/internacional/event</link><pubDate>Thu, 19 Nov 2026 10:00:00 GMT</pubDate></item>
        </channel></rss>'''
        response = MagicMock()
        response.__enter__.return_value.read.return_value = xml
        with patch.object(app.urllib.request, 'urlopen', return_value=response):
            items = app.fetch_feed({'url': 'https://example.org/rss', 'name': 'Test',
                                    'include_url': '/espana/'}, self.now, 7)
        self.assertEqual([item['title'] for item in items], ['National event'])

    def test_news_block_is_spanish_but_learning_sections_remain_english(self):
        selected = app.select_questions(app.load_banks(), {}, 3)
        story = self.item('El Congreso debate medidas de vivienda', source='Medio español')
        body, plain = app.render_email(self.now.date(), selected, [story], '')
        self.assertIn('lang="es"', body)
        self.assertIn('19 de noviembre de 2026', body)
        self.assertIn('Actualidad de España', body)
        self.assertIn('Neuroscience', plain)
        self.assertNotIn('Ireland’s News', body)
        self.assertNotIn('social justice editorial priorities', plain)

    def test_unsafe_schemes_are_rejected(self):
        with self.assertRaises(ValueError):
            app.safe_url('javascript:alert(1)')

    def test_embedded_html_doctype_is_allowed_but_real_xml_dtd_is_rejected(self):
        rss = b'''<rss><channel><item><title>Vivienda</title><link>https://example.org/article</link>
        <pubDate>Thu, 19 Nov 2026 10:00:00 GMT</pubDate>
        <description><![CDATA[<!doctype html><p>Embedded article</p>]]></description>
        </item></channel></rss>'''
        response = MagicMock()
        response.__enter__.return_value.read.return_value = rss
        source = {'url': 'https://example.org/rss', 'name': 'Test'}
        with patch.object(app.urllib.request, 'urlopen', return_value=response):
            self.assertEqual(len(app.fetch_feed(source, self.now, 7)), 1)
        response.__enter__.return_value.read.return_value = b'<!DOCTYPE rss [<!ENTITY test "x">]>' + rss
        with patch.object(app.urllib.request, 'urlopen', return_value=response):
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                app.fetch_feed(source, self.now, 7)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(app.ROOT / 'content', self.root / 'content')
        shutil.copytree(app.ROOT / 'config', self.root / 'config')
        self.root_patch = patch.object(app, 'ROOT', self.root)
        self.root_patch.start()
        self.env_patch = patch.dict(os.environ, {
            'EMAIL_REMITENTE': 'sender@example.org', 'EMAIL_PASSWORD': 'fake-test-secret',
            'EMAIL_DESTINATARIOS': 'matt@example.org', 'URL_WEB': '', 'MODO_PRUEBA': '0'})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()
        self.root_patch.stop()
        self.tmp.cleanup()

    def test_preview_does_not_send_or_write_real_history(self):
        with patch.object(app, 'send_email') as smtp:
            app.main(['--demo', '--offline', '--date', '2026-11-20'])
        smtp.assert_not_called()
        self.assertFalse((self.root / 'state').exists())
        self.assertEqual(len(list((self.root / 'previews/archive/editions').glob('*.html'))), 4)

    def test_success_is_recorded_and_second_run_does_not_send(self):
        with patch.object(app, 'send_email') as smtp, patch.object(app, 'collect_news', return_value=([], 'No news')):
            app.main(['--send'])
            app.main(['--send'])
        smtp.assert_called_once()
        history = json.loads((self.root / 'state/history.json').read_text())
        self.assertEqual(len(history['questions']), len(app.SECTIONS) * 3)
        self.assertEqual(len(history['editions']), 1)
        self.assertFalse((self.root / 'state/pending.json').exists())
        self.assertTrue((self.root / 'docs/index.html').exists())

    def test_ambiguous_smtp_failure_blocks_automatic_retry(self):
        with patch.object(app, 'collect_news', return_value=([], 'No news')):
            with patch.object(app, 'send_email', side_effect=smtplib.SMTPServerDisconnected('lost connection')):
                with self.assertRaises(smtplib.SMTPServerDisconnected):
                    app.main(['--send'])
            self.assertTrue((self.root / 'state/pending.json').exists())
            self.assertFalse((self.root / 'state/history.json').exists())
            with patch.object(app, 'send_email') as smtp:
                with self.assertRaisesRegex(RuntimeError, 'pending'):
                    app.main(['--send'])
                smtp.assert_not_called()

    def test_corrupted_history_stops_before_smtp(self):
        (self.root / 'state').mkdir()
        (self.root / 'state/history.json').write_text('{broken')
        with patch.object(app, 'send_email') as smtp:
            with self.assertRaises(ValueError):
                app.main(['--send'])
            smtp.assert_not_called()

    def test_send_rejects_preview_overrides(self):
        with self.assertRaises(SystemExit):
            app.main(['--send', '--offline'])

    def test_recipient_privacy_and_plain_text_alternative(self):
        with patch.object(app.smtplib, 'SMTP_SSL') as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value = {}
            app.send_email('Weekly quiz', ('<p>HTML</p>', 'Plain text'), '2026-W47')
            call = smtp.return_value.__enter__.return_value.send_message.call_args
            message = call.args[0]
            self.assertEqual(message['To'], 'sender@example.org')
            self.assertNotIn('matt@example.org', str(message))
            self.assertEqual(call.kwargs['to_addrs'], ['matt@example.org'])
            self.assertEqual([p.get_content_type() for p in message.iter_parts()], ['text/plain', 'text/html'])


if __name__ == '__main__':
    unittest.main()
