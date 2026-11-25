import io
import json
import unittest
import zipfile
import dashboard_upload_audit as audit


class ReviewPrivacyMetadataTests(unittest.TestCase):
    def fixture(self, privacy=None, extra=None):
        body = json.dumps({'as_of':'2026-11-23','futures_contract':'F202612',
                           'charts':[], 'downloads':[{'file':'review.zip'}]}).encode()
        public = {'latest.json':body}
        manifest = {'as_of':'2026-11-23','contract':'F202612',
                    'files':[{'file':name,'sha256':audit.sha(value)} for name,value in public.items()]}
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr('latest.json',body)
            z.writestr('review_manifest_20261123.json',json.dumps(manifest))
            if privacy is not None:z.writestr('PUBLIC_PRIVACY_MANIFEST.json',json.dumps(privacy))
            if extra:z.writestr(extra,b'unapproved')
        return out.getvalue(),body,public

    def privacy(self, source_key='source_copy_sha256'):
        _,body,_=self.fixture()
        return {'scope':'Published copies only; originals preserved',
                'redacted_files':[{'file':'latest.json',source_key:'a'*64,'public_sha256':audit.sha(body)}]}

    def verify(self, privacy=None, extra=None):
        archive,body,public=self.fixture(privacy,extra)
        return audit.verify_review_bundle(archive,body,'review.zip',public.__getitem__)

    def test_existing_bundle_without_metadata_remains_valid(self):
        self.assertEqual(self.verify()['privacy_metadata_verified'],[])

    def test_known_redaction_metadata_is_checked(self):
        for key in ['source_copy_sha256','original_sha256']:
            self.assertEqual(self.verify(self.privacy(key))['privacy_metadata_verified'],['latest.json'])

    def test_unknown_extra_file_still_rejected(self):
        with self.assertRaisesRegex(ValueError,'목록'):
            self.verify(self.privacy(),'private_raw.json')

    def test_wrong_public_hash_rejected(self):
        p=self.privacy();p['redacted_files'][0]['public_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'해시'):
            self.verify(p)

    def test_outside_or_duplicate_record_rejected(self):
        p=self.privacy();p['redacted_files'][0]['file']='../secret.json'
        with self.assertRaisesRegex(ValueError,'파일'):
            self.verify(p)
        p=self.privacy();p['redacted_files']*=2
        with self.assertRaisesRegex(ValueError,'파일'):
            self.verify(p)

    def test_invalid_source_hash_or_shape_rejected(self):
        for bad in ['', 'not-a-hash', None]:
            p=self.privacy();p['redacted_files'][0]['source_copy_sha256']=bad
            with self.assertRaisesRegex(ValueError,'해시'):
                self.verify(p)
        with self.assertRaisesRegex(ValueError,'형식'):
            self.verify({'scope':'x','redacted_files':[]})

    def test_content_tampering_still_rejected(self):
        archive,body,public=self.fixture(self.privacy());public['latest.json']+=b'changed'
        with self.assertRaisesRegex(ValueError,'해시'):
            audit.verify_review_bundle(archive,body,'review.zip',public.__getitem__)


if __name__=='__main__':unittest.main()
