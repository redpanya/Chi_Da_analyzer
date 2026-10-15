"""경계 문맥 병합: 양쪽 근거·동일 주제 판단·취소 체크포인트."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from archive import context_merge as merge


def item(start,id):
    speech={'id':id,'kind':'speech','start_ms':start,'end_ms':start+1000,'text':'다음 규칙을 이야기한다.','speaker':'화자 미분석'}
    return {'start_ms':start,'end_ms':start+1000,'input':{'range':{'chat_offset_ms':0},'notes':[],'evidence':[speech]},
            'summary':{'title':'신청 규칙','context':[{'text':'신청 규칙을 설명한다.','evidence':[id]}],'chat':[],'relation':[],'uncertainties':[]}}

class MergeTests(unittest.TestCase):
    def test_same_topic_joins_across_processing_boundary(self):
        left,right=item(0,'S1_1'),item(120000,'S2_1');summary={'title':'신청 규칙','context':'신청 순서와 후속 규칙을 함께 설명한다.','chat':'','relation':''}
        job=Mock();job.infer_value.return_value=({'merge':True,'summary':summary},4)
        combined,seconds=merge.merge_pair(job,left,right,Path('/unused'))
        self.assertEqual((combined['start_ms'],combined['end_ms']),(0,121000));self.assertTrue(combined['merged']);self.assertEqual(seconds,4)
        self.assertEqual({r['id'] for r in combined['input']['evidence']},{'S1_1','S2_1'})
    def test_different_topic_and_unsupported_merge_rejected(self):
        left,right=item(0,'S1_1'),item(120000,'S2_1');job=Mock()
        job.infer_value.return_value=({'merge':False,'summary':None},1)
        self.assertIsNone(merge.merge_pair(job,left,right,Path('/unused'))[0])
        job.infer_value.return_value=({'merge':True,'summary':{'title':'빈 문맥','context':'','chat':'','relation':''}},1)
        with self.assertRaises(ValueError):merge.merge_pair(job,left,right,Path('/unused'))
        job.infer_value.return_value=({'merge':'yes','summary':None},1)
        with self.assertRaises(ValueError):merge.merge_pair(job,left,right,Path('/unused'))
