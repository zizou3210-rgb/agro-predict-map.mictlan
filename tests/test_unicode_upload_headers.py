import io
import json
import threading
import unittest
from email.message import Message
from http.server import ThreadingHTTPServer
from urllib.parse import quote
from urllib.request import Request, urlopen

from server import AppRequestHandler


def encoded_headers(values):
    return {**{name: quote(value, safe="~!*'()") for name, value in values.items()}, 'X-Upload-Header-Encoding': 'uri-component-v1'}


def handler_with_headers(values, body=b'test'):
    handler = object.__new__(AppRequestHandler)
    handler.headers = Message()
    for name, value in values.items():
        handler.headers[name] = value
    handler.headers['Content-Length'] = str(len(body))
    handler.rfile = io.BytesIO(body)
    return handler


class UnicodeUploadHeaderTests(unittest.TestCase):
    def test_unicode_filename_and_columns_roundtrip(self):
        values = {'X-File-Name': 'Predicción – maíz 🌽 100%.xlsx', 'X-Selected-Id-Header': 'Finca – región 東京'}
        handler = handler_with_headers(encoded_headers(values))
        self.assertEqual(handler.read_upload_request(), (values['X-File-Name'], b'test'))
        self.assertEqual(handler.read_text_header('X-Selected-Id-Header'), values['X-Selected-Id-Header'])

    def test_selected_names_and_column_lists_keep_unicode(self):
        names = ['Maíz 🌽', 'Variedad – α', '東京']
        handler = handler_with_headers(encoded_headers({'X-Selected-Germplasm-Names': json.dumps(names, ensure_ascii=False), 'X-Identifier-Columns': json.dumps(names, ensure_ascii=False)}))
        self.assertEqual(handler.parse_selected_germplasm_names_header(), names)
        self.assertEqual(handler.parse_json_list_header('X-Identifier-Columns'), names)

    def test_legacy_clients_do_not_decode_literal_percent_sequences(self):
        handler = handler_with_headers({'X-File-Name': 'trial%20literal.xlsx', 'X-Selected-Id-Header': 'Farm'})
        self.assertEqual(handler.read_upload_request()[0], 'trial%20literal.xlsx')
        self.assertEqual(handler.read_text_header('X-Selected-Id-Header'), 'Farm')

    def test_encoded_percent_sequences_are_decoded_only_once(self):
        handler = handler_with_headers(encoded_headers({'X-File-Name': 'trial%20literal.xlsx'}))
        self.assertEqual(handler.read_upload_request()[0], 'trial%20literal.xlsx')

    def test_invalid_utf8_and_header_controls_are_rejected(self):
        for value in ['%FF.xlsx', 'bad%0D%0Aname.xlsx', 'bad%00name.xlsx']:
            handler = handler_with_headers({'X-File-Name': value, 'X-Upload-Header-Encoding': 'uri-component-v1'})
            with self.assertRaises(ValueError):
                handler.read_upload_request()

    def test_http_upload_preserves_file_bytes_and_unicode_metadata(self):
        class Handler(AppRequestHandler):
            def do_POST(self):
                source, body = self.read_upload_request()
                self.send_json({'source_name': source, 'body': body.decode(), 'target': self.read_text_header('X-Target-Column'), 'names': self.parse_selected_germplasm_names_header()})
            def log_message(self, *_args):
                pass
        from functools import partial
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory='.'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            values = {'X-File-Name': 'datos – maíz 🌽.xlsx', 'X-Target-Column': 'Rendimiento ≥ 5', 'X-Selected-Germplasm-Names': json.dumps(['α–β'], ensure_ascii=False)}
            request = Request(f'http://127.0.0.1:{server.server_port}/upload', data=b'original-file-bytes', headers=encoded_headers(values), method='POST')
            with urlopen(request, timeout=5) as response:
                payload = json.load(response)
            self.assertEqual(payload, {'source_name': values['X-File-Name'], 'target': values['X-Target-Column'], 'body': 'original-file-bytes', 'names': ['α–β']})
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
