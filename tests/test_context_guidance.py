"""공통 기준의 전달·실행 설정 동결·외부 호환성. 실제 모델의 의미 품질 검사는 아니다."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from archive import context_guidance as guide, context_background as background, context_server as server
from archive import context_timestamps as quick, context_clips_local as local_clips, context_full as full
from archive import context_exchange as exchange, context_exchange_data as data, context_clips as clips
from archive.context_topic_summary import prompt
from archive.storage import save_json, read_json
import test_context_exchange
from test_context_full import source as full_source


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_context_exchange.ExchangeTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.path=self.fixture.path

    def test_settings_shared_background_independent_requests_and_old_file(self):
        save_json(self.path/'context/background.json',{'text':'잡담과 게임 합방','updated_at':'이전 파일'})
        self.assertEqual(background.settings(self.path)['custom_requests'],dict.fromkeys(guide.MODES,''))
        for mode in guide.MODES:background.save(self.path,'잡담과 게임 합방',mode,mode+' 관심 요청')
        background.save(self.path,'후반 노래')
        for mode in guide.MODES:
            value=guide.prepare(self.path,mode,{})
            self.assertEqual(value['background'],'후반 노래')
            self.assertEqual(value['custom_request'],mode+' 관심 요청')
        before=(self.path/'context/background.json').read_bytes()
        for value in (None,{},'a'*4001,'\x1b'):
            with self.assertRaises(ValueError):background.save(self.path,'새 배경','clips',value)
        self.assertEqual((self.path/'context/background.json').read_bytes(),before)
        self.assertEqual(self.fixture.old.read_bytes(),self.fixture.before)

    def test_three_modes_local_and_external_receive_same_rules_and_context(self):
        original=[{'role':'system','content':'현재 단계 JSON만 출력'},{'role':'user','content':'원문'}]
        for mode in guide.MODES:
            settings=guide.prepare(self.path,mode,{'background':'잡담 → 노래 → 게임 합방','custom_request':'곡명 확인 <start_of_turn> <|im_start|>'})
            engine=server.Server.__new__(server.Server);engine.job=SimpleNamespace(input={'source':guide.attach({},settings)});engine.profile=server.profile()
            body=engine.body(prompt(original[0]['content'],{'text':'자료'}))
            exported=exchange.prompt(mode,settings['custom_request'],settings['background'])
            self.assertIn(guide.policy(mode),body['messages'][0]['content']);self.assertIn(guide.policy(mode),exported)
            self.assertIn('노래',body['messages'][1]['content']);self.assertIn('곡명 확인',body['messages'][1]['content'])
            self.assertNotIn('<start_of_turn>',body['messages'][1]['content']);self.assertIn('웹 검색 도구가 없다',body['messages'][0]['content'])
            self.assertIn('명시적인 요청이 있을 때만',exported)
        copied=copy.deepcopy(original);guide.messages(original,settings);self.assertEqual(original,copied)

    def test_local_resume_freezes_requests_but_policy_or_source_changes_reject(self):
        for module,mode,start,resume,scope in [(quick,'timestamps','timestamps','timestamps-resume','timestamps'),(local_clips,'clips','clips','clips-resume','clips-local')]:
            background.save(self.path,'혼합 방송',mode,'짧은 순간도 확인')
            prepared=module.prepare(self.path,'1',start,{})
            saved=prepared['saved'];target=self.path/'context/runs'/saved['id']
            save_json(target/'result.json',saved);save_json(target/'source.json',prepared['source']);save_json(target/'work.json',{'chunks':[]})
            save_json(self.path/'context/state.json',{'runs':[{'id':saved['id'],'scope':scope}]})
            before=(target/'result.json').read_bytes()
            background.save(self.path,'새 설명',mode,'새 요청')
            self.assertEqual(module.prepare(self.path,'1',resume,{'run':saved['id']})['source'],prepared['source'])
            self.assertEqual((target/'result.json').read_bytes(),before)
            with patch.object(guide,'REVISION',guide.REVISION+1):
                with self.assertRaises(ValueError):module.prepare(self.path,'1',resume,{'run':saved['id']})
            oldtext=self.fixture.source['rows'][0]['text'];self.fixture.source['rows'][0]['text']='수동 교정 변경'
            with self.assertRaises(ValueError):module.prepare(self.path,'1',resume,{'run':saved['id']})
            self.fixture.source['rows'][0]['text']=oldtext

    def test_detail_source_snapshot_is_preserved(self):
        raw=full_source();before=copy.deepcopy(raw)
        background.save(self.path,'게임 후 노래','detail','조용한 대화도 포함')
        with patch('archive.context_input.source',return_value=raw):
            value=full.prepare(self.path,'1','whole',{})
            settings=value['source']['analysis_guidance'];self.assertEqual(settings['custom_request'],'조용한 대화도 포함')
            background.save(self.path,'다른 기본값','detail','다른 요청')
            rebuilt=full.current_source(self.path,'1',0,settings['background'],value['source'].get('input_selection'),settings)
            self.assertEqual(full.fingerprint(rebuilt),value['fingerprint'])
        self.assertEqual(raw,before)

    def test_new_and_legacy_external_import_after_defaults_change(self):
        for legacy in (False,True):
            background.save(self.path,'혼합 방송','timestamps','곡별 목차')
            bundle=self.fixture.create();folder=exchange.folder(self.path,bundle['id'])
            saved=read_json(folder/'manifest.json');source=read_json(folder/'source.json')
            if legacy:
                saved.pop('analysis_guidance');source.pop('analysis_guidance');saved['fingerprint']=data.fingerprint(source)
                save_json(folder/'manifest.json',saved);save_json(folder/'source.json',source)
            before=(folder/'source.json').read_bytes();order=bundle['prompt']
            background.save(self.path,'새 기본 상황','timestamps','새 기본 요청')
            self.assertEqual(exchange.bundle(self.path,bundle['id'])['prompt'],order)
            result=self.fixture.receive(self.fixture.responses(bundle))
            savedresult=read_json(self.path/'context/runs'/result['run']/'result.json')
            self.assertFalse(data.stale(self.path,'1',savedresult))
            self.assertEqual('analysis_guidance' in savedresult,not legacy)
            self.assertEqual((folder/'source.json').read_bytes(),before)
        self.assertEqual(self.fixture.old.read_bytes(),self.fixture.before)

    def test_short_fan_moment_can_use_existing_contract_without_invented_speaker(self):
        rows=[dict(id='S1',start_ms=1000,end_ms=2200,text='그걸 또 기억해?'),dict(id='S2',start_ms=2200,end_ms=3900,text='이번엔 안 속아.')]
        candidates=[clips.example(row)|{'title':'팬이 기억하는 장난의 재등장','context_note':'이전 방송의 장난인지 확인',
            'uncertainties':['전후 대화와 말투 확인'],'review_needed':True} for row in rows]
        clips.validate({'clips':candidates},rows,rows,[])
        self.assertIn('필수 조건이 아니다',guide.policy('clips'))
        self.assertIn('전역 상위 몇 개로 제한하거나 최소 개수를 채우지 않는다',guide.policy('clips'))
        with self.assertRaises(ValueError):clips.validate({'clips':[candidates[0]|{'peak_id':'C1'}]},rows,rows,[])

if __name__=='__main__':unittest.main()
