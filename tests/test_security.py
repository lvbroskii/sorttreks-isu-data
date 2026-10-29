"""Public-capture credential hygiene; values are synthetic, never real secrets."""
import gzip
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from isu_pilot.security import public_body
from isu_pilot.sources import Client
from isu_pilot.archive import Archive

ROOT=Path(__file__).resolve().parents[1]


class PublicCaptureTests(unittest.TestCase):
    def test_plain_and_flight_escaped_fields_redacted_without_changing_rounds(self):
        fake='synthetic-'+'fixture-value-only'
        raw=json.dumps({'access_token':fake,'token_type':'bearer','event_result_round_id':123,'start_time':'2026-10-30T13:00:00Z'}).encode()
        clean=public_body(raw)
        self.assertNotIn(fake.encode(),clean);self.assertEqual(json.loads(clean)['event_result_round_id'],123)
        escaped=json.dumps(raw.decode()).encode()
        self.assertNotIn(fake.encode(),public_body(escaped))
        self.assertEqual(public_body(clean),clean)
    def test_client_returns_only_public_safe_body_and_records_original_hash(self):
        fake='synthetic-'+'fixture-value-only'
        body=json.dumps({'access_token':fake,'data':[]}).encode()
        class Response(io.BytesIO):
            url='https://front-api.isu.org/test';status=200;headers={'Content-Type':'application/json'}
        with tempfile.TemporaryDirectory() as td:
            c=Client(td,transport=lambda *a,**k:Response(body))
            clean,rec=c.get(Response.url)
            self.assertNotIn(fake.encode(),clean)
            self.assertTrue(rec['credentialsRedacted'])
            self.assertEqual(rec['originalResponseSha256'],hashlib.sha256(body).hexdigest())
            self.assertEqual(rec['sha256'],hashlib.sha256(clean).hexdigest())
    def test_archive_refuses_unsanitized_legacy_body(self):
        body=json.dumps({'refresh_token':'synthetic-'+'fixture-value-only'}).encode()
        with tempfile.TemporaryDirectory() as td:
            a=Archive(td)
            with self.assertRaisesRegex(ValueError,'Credential'):a.add(body)
    def test_tracked_public_captures_have_no_unredacted_credential_fields(self):
        for name in subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'):
            if not name:continue
            p=ROOT/name
            if not p.is_file():continue
            raw=gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes()
            if name.startswith(('fixtures/','examples/')):
                self.assertEqual(public_body(raw),raw,'Unsanitized public capture: '+name)
