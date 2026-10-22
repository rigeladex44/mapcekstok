import asyncio
import os
import shutil
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import BOT_STOK as bot


class ParsingTests(unittest.TestCase):
    def test_thousands(self):
        for text, expected in [('1.820 Tabung', 1820), ('1,820 Tbg', 1820), ('0', 0), ('Tidak Diketahui', -1)]:
            self.assertEqual(bot.angka_awal(text), expected)

    def test_missing_category_does_not_borrow_next_number(self):
        text = 'Rumah Tangga\nBelum tersedia\nUsaha Mikro\n18 Tbg\nTotal Tabung Terjual\n1.820 Tbg'
        self.assertEqual(bot.report_value(text, 'Rumah Tangga'), 'Tidak Diketahui')
        self.assertEqual(bot.report_value(text, 'Usaha Mikro'), '18')
        self.assertEqual(bot.report_value(text, 'Total Tabung Terjual'), '1820')

    def test_chunks_keep_html_and_entities_complete(self):
        text = '<b>Nama</b>\n' + '&amp;' * 2000
        chunks = bot.telegram_chunks(text)
        self.assertTrue(all(len(c) <= 3900 for c in chunks))
        from html import unescape
        self.assertEqual(''.join(unescape(c) for c in chunks), 'Nama\n' + '&' * 2000)


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_failures_without_repeating_successes(self):
        calls = {}
        async def worker(browser, email, pin):
            calls[email] = calls.get(email, 0) + 1
            if email == 'retry' and calls[email] == 1:
                raise asyncio.TimeoutError
            if email == 'always-fails' or (email == 'retry' and calls[email] < 3):
                return None
            return email, '10'
        browser = SimpleNamespace(close=AsyncMock())
        manager = AsyncMock()
        manager.__aenter__.return_value = SimpleNamespace(chromium=SimpleNamespace(launch=AsyncMock(return_value=browser)))
        with patch.object(bot, 'async_playwright', return_value=manager), patch.object(bot.asyncio, 'sleep', new=AsyncMock()):
            results, failures = await bot.process_batch_async(
                [('ok', 'private'), ('retry', 'private'), ('always-fails', 'private'), ('ok', 'private')], worker)
        self.assertEqual(calls, {'ok': 1, 'retry': 3, 'always-fails': 3})
        self.assertEqual(len(results), 2)
        self.assertEqual(failures, ['always-fails'])
        browser.close.assert_awaited_once()

    async def test_cancelled_login_closes_context(self):
        context = SimpleNamespace(new_page=AsyncMock(side_effect=asyncio.CancelledError), close=AsyncMock())
        browser = SimpleNamespace(new_context=AsyncMock(return_value=context))
        with self.assertRaises(asyncio.CancelledError):
            await bot._login_and_setup(browser, 'test', 'private')
        context.close.assert_awaited_once()

    async def test_cancelled_stock_worker_closes_context(self):
        context = SimpleNamespace(close=AsyncMock())
        with patch.object(bot, '_login_and_setup', new=AsyncMock(return_value=(context, object(), 'name'))), patch.object(bot, 'read_stock', new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await bot.cek_stok_satu_async(None, 'test', 'private')
        context.close.assert_awaited_once()

    async def test_overlapping_job_rejected(self):
        bot.active_jobs.add('test-chat')
        try:
            with patch.object(bot, '_process_user_request', new=AsyncMock()) as process, patch.object(bot, 'tg_send_async', new=AsyncMock()):
                await bot.process_user_request('test-chat', '', 'WAITING_JP')
                process.assert_not_awaited()
        finally:
            bot.active_jobs.clear()


class StockDOMTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from playwright.async_api import async_playwright
        self.manager = await async_playwright().start()
        self.browser = await self.manager.chromium.launch(executable_path=os.getenv('TEST_CHROMIUM_PATH') or shutil.which('chromium'), headless=True)
        self.page = await self.browser.new_page()

    async def asyncTearDown(self):
        await self.browser.close()
        await self.manager.stop()

    async def test_sales_quantity_before_stock_is_ignored(self):
        await self.page.set_content('<div>Total Tabung Terjual <span>1.820 Tabung</span></div><section><label>Stok Akhir</label><strong>120 Tabung</strong></section>')
        self.assertEqual(await bot.read_stock(self.page), '120')

    async def test_zero_stock_and_hidden_old_counter(self):
        await self.page.set_content('<section style="display:none">Stok Akhir <b>900 Tabung</b></section><section>Stok Akhir <b>0 Tabung</b></section>')
        self.assertEqual(await bot.read_stock(self.page), '0')

    async def test_ambiguous_stock_is_failure(self):
        await self.page.set_content('<section>Stok Akhir <b>10 Tabung</b></section><section>Stok Tersedia <b>20 Tabung</b></section>')
        with patch.object(self.page, 'wait_for_timeout', new=AsyncMock()):
            with self.assertRaises(RuntimeError):
                await bot.read_stock(self.page)


if __name__ == '__main__':
    unittest.main()
