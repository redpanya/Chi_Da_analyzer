"""반응의 의미 상태, 근거 거부, 같은 사건 병합과 실패 재시도를 검사한다."""
import tempfile,threading,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from archive import context_events as events,context_evidence as ev


class EventTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.job=Mock(stop=threading.Event());self.source={'duration_ms':120000,'chat_offset_ms':0,'notes':['전체 제공 채팅'],
            'speech':[{'id':str(i),'start_ms':i*10000,'end_ms':i*10000+8000,'text':'가격이 비싸다.'} for i in range(12)],
            'chat':[{'offset_ms':t,'text':'가격이 비싸요','message_type':'donation'} for t in (41000,42000,43000,71000,72000)]}
        self.rows=ev.speech(self.source);self.stories=[{'id':'story-0','parent_id':'topic-0','start_ms':0,'end_ms':120000,'title':'가격 비교'}]
    def tearDown(self):self.temp.cleanup()
    def infer(self,value,folder,prompt,schema,status='linked',same='none'):
        speech=[r for r in value['evidence'] if r['kind']=='speech'];chat=[r for r in value['evidence'] if r['kind']=='chat']
        return {'status':status,'same_as':same,'speech_id':speech[0]['id'] if status=='linked' else 'none',
            'chat_id':chat[0]['id'],
            'title':'가격에 대한 반응','observation':'가격이 비싸다는 채팅이 나왔다.',
            'reason':'가격 비교 발언에 같은 가격을 언급한다.'},1
    def inspect(self,status='linked',same=False):
        candidates=[{'id':'reaction-0','peak_ms':40000}]+([{'id':'reaction-1','peak_ms':70000}] if same else [])
        self.job.infer_value.side_effect=lambda *a:self.infer(*a,status=status,same='reaction-0' if same and 'reaction-0' in a[3]['properties']['same_as']['enum'] else 'none')
        with patch.object(events,'candidates',return_value=candidates):return events.inspect(self.job,self.folder,self.source,self.rows,self.stories,{})
    def test_linked_requires_speech_and_chat_and_other_states_have_no_parent(self):
        for status in ('linked','other','mixed','unknown'):
            with self.subTest(status=status):
                folder=self.folder/status;folder.mkdir();self.folder=folder
                result=self.inspect(status)[0]
                self.assertEqual(result['parent_id'],'topic-0' if status=='linked' else None)
                self.assertEqual(bool(result['summary']['relation']),status=='linked')
                self.assertEqual(result['relation_status'],status)
                self.assertIn('donation',self.job.infer_value.call_args.args[2])
    def test_same_event_keeps_new_range_evidence_without_duplicate_chat_counts(self):
        result=self.inspect(same=True);self.assertEqual(len(result),1);event=result[0]
        self.assertIn('"status":"linked"',self.job.infer_value.call_args.args[2])
        self.assertIn('"story":"story-0"',self.job.infer_value.call_args.args[2])
        self.assertEqual(event['signal_ids'],['reaction-0','reaction-1'])
        self.assertGreaterEqual(event['end_ms'],71000)
        self.assertEqual(event['input']['stats']['chat_used'],5)
        ids={r['id'] for r in event['input']['evidence']}
        self.assertTrue(all(ref in ids for name in ('context','chat','relation') for claim in event['summary'][name] for ref in claim['evidence']))
    def test_bad_model_response_retries_once_and_success_reuses_checkpoint(self):
        self.job.infer_value.side_effect=[({'id':'absent'},1),({'id':'S0'},2)]
        validate=lambda raw:ev.refs([raw['id']],self.rows,{'speech'})
        result=ev.call(self.job,self.folder,'retry',{},'검사',{},ev.obj({'id':ev.string()}),validate)
        self.assertEqual(result,{'id':'S0'});self.assertEqual(self.job.infer_value.call_count,2)
        ev.call(self.job,self.folder,'retry',{},'검사',{},ev.obj({'id':ev.string()}),validate)
        self.assertEqual(self.job.infer_value.call_count,2)
        self.job.infer_value.side_effect=[({'id':'absent'},1),({'id':'absent'},1)]
        with self.assertRaises(ValueError):ev.call(self.job,self.folder,'invalid',{},'검사',{},ev.obj({'id':ev.string()}),validate)
        self.assertFalse((self.folder/'invalid.json').exists())
    def test_laugh_only_cannot_be_used_to_claim_a_cause(self):
        for row in self.source['chat']:row['text']='ㅋㅋㅋㅋ 🤣'
        result=self.inspect()[0]
        self.assertEqual(result['relation_status'],'unknown');self.assertIsNone(result['parent_id'])
        self.assertEqual(result['summary']['context'],[]);self.assertEqual(result['summary']['relation'],[])
        self.assertEqual(result['summary']['chat'][0]['text'],'채팅 원문: ㅋㅋㅋㅋ 🤣')
        self.assertEqual(self.job.infer_value.call_count,1)
    def test_uncertain_laughter_does_not_merge_as_the_same_causal_event(self):
        for row in self.source['chat']:row['text']='ㅋㅋㅋㅋ'
        result=self.inspect(same=True)
        self.assertEqual(len(result),2)
        self.assertTrue(all(r['relation_status']=='unknown' for r in result))
    def test_missing_speech_reference_cannot_link(self):
        def missing(*args):
            raw,seconds=self.infer(*args);raw.update(speech_id='none');return raw,seconds
        self.job.infer_value.side_effect=missing
        with patch.object(events,'candidates',return_value=[{'id':'reaction-0','peak_ms':40000}]):
            result=events.inspect(self.job,self.folder,self.source,self.rows,self.stories,{})[0]
        self.assertEqual(result['relation_status'],'unknown');self.assertIsNone(result['parent_id'])

    def test_quotes_are_copied_from_source_not_generated(self):
        for r in self.source['speech']:r['text']='쿠리만주를 이야기한다.'
        self.rows=ev.speech(self.source)
        for r in self.source['chat']:r['text']='쿠리만쥬 성우가 쿠리만쥬 같아요'
        result=self.inspect()[0]
        schema=self.job.infer_value.call_args.args[3]['properties']
        self.assertNotIn('chat_excerpt',schema);self.assertNotIn('speech_excerpt',schema)
        self.assertEqual(result['summary']['context'][0]['text'],'발언 원문: 쿠리만주를 이야기한다.')
        self.assertIn('쿠리만쥬 성우가 쿠리만쥬 같아요',[r['text'] for r in result['input']['evidence']])

    def test_bad_reference_marks_failure_and_continues_then_resume_recovers(self):
        candidates=[{'id':'reaction-0','peak_ms':40000},{'id':'reaction-1','peak_ms':70000}]
        calls=[];published=[]
        def invalid_twice(*args):
            raw,seconds=self.infer(*args);calls.append(1)
            if len(calls)<=2:raw['chat_id']='S0'
            return raw,seconds
        self.job.infer_value.side_effect=invalid_twice
        with patch.object(events,'candidates',return_value=candidates):
            result=events.inspect(self.job,self.folder,self.source,self.rows,self.stories,{},publish=lambda rows:published.append(len(rows)))
            self.assertEqual([r['relation_status'] for r in result],['failed','linked'])
            self.assertEqual(result[0]['summary']['relation'],[]);self.assertEqual(published,[1,2])
            self.job.infer_value.side_effect=self.infer
            recovered=events.inspect(self.job,self.folder,self.source,self.rows,self.stories,{})
            self.assertTrue(all(r['relation_status']=='linked' for r in recovered))

    def test_infrastructure_and_cancellation_are_not_swallowed(self):
        from archive.source import Cancelled
        for error in (OSError('공간 부족'),ValueError('엔진 종료'),Cancelled()):
            self.job.infer_value.reset_mock();self.job.infer_value.side_effect=error
            with patch.object(events,'candidates',return_value=[{'id':'reaction-0','peak_ms':40000}]):
                with self.assertRaises(type(error)):events.inspect(self.job,self.folder,self.source,self.rows,self.stories,{})
            self.assertEqual(self.job.infer_value.call_count,1)

    def test_link_uses_speech_story_even_when_reaction_peak_is_later(self):
        self.stories=[{'id':'story-0','parent_id':'topic-0','start_ms':0,'end_ms':30000},
                      {'id':'story-1','parent_id':'topic-1','start_ms':30000,'end_ms':120000}]
        result=self.inspect()[0]
        self.assertEqual(result['story_id'],'story-0')
        self.assertEqual(result['summary']['context'][0]['text'],'발언 원문: 가격이 비싸다.')


if __name__=='__main__':unittest.main()
