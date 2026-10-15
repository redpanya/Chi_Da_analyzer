import copy
import unittest
from unittest.mock import patch
from archive import context_uncertainty as policy,context_dialogue_input as di,context_dialogue_model as dm,context_full
from archive.storage import read_json,save_json
import test_context_dialogue as fixture


class UncertaintyTests(unittest.TestCase):
    setUp=fixture.DialogueTests.setUp
    job=fixture.DialogueTests.job
    infer=fixture.DialogueTests.infer
    execute=fixture.DialogueTests.execute

    def test_unknown_kept_separate_from_text_error_and_original_unchanged(self):
        self.source['speech'][0].update(status='failed',speaker_name='화자인식 실패')
        self.source['speech'][1].update(status='failed',speaker_name='화자인식 실패')
        self.source['speech'][2].update(status='confirmed')
        self.source['speech'][3].update(encoding_review=True)
        before=copy.deepcopy(self.source);rows=policy.rows(self.source)
        self.assertEqual(len(rows),8)
        self.assertNotEqual(rows[0]['speaker_tag'],rows[1]['speaker_tag'])
        self.assertTrue(rows[2]['speaker_tag'].startswith('확인 '))
        text=policy.dialogue_prompt(rows,None)
        self.assertIn('같은 사람인지 다른 사람인지 모른다',text);self.assertIn('전체 합의로 바꾸지 않는다',text)
        result=self.execute(self.job());self.assertEqual(result['speaker_policy'],1)
        self.assertEqual(result['contract']['speaker_policy'],1);self.assertEqual(self.source,before)

    def test_legacy_resume_uses_old_prompt_and_contract(self):
        job=self.job();job.input['speaker_policy']=0
        count=[0]
        def cancel(value,*args):
            count[0]+=1
            if count[0]==2:job.cancel()
            return self.infer(value,*args)
        old=self.execute(job,cancel);self.assertNotIn('speaker_policy',old)
        resume=self.job('resume');self.assertEqual(resume.input['speaker_policy'],0)
        with patch.object(policy,'dialogue_prompt',side_effect=AssertionError('구버전 프롬프트 변경')):
            result=self.execute(resume)
        self.assertTrue(result['complete']);self.assertEqual(result['contract'],old['contract'])
        self.assertNotIn('speaker_policy',result)


if __name__=='__main__':unittest.main()
