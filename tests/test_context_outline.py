import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from archive import context_outline as outline


class ShortStoryTests(unittest.TestCase):
    def review(self,decisions):
        rows=[dict(id=f'S{i}',kind='speech',start_ms=i*10000,end_ms=(i+1)*10000,text=t) for i,t in enumerate(['사건 설명','응?','설명이 이어짐','새 이야기'])]
        items=[dict(start=r['id'],start_ms=r['start_ms'],title=r['text']) for r in rows]
        seen=[]
        def infer(job,folder,key,value,instruction,data,schema,validate):
            result={'decision':decisions.get(key,'keep'),'reason':'앞뒤 원문 근거'};validate(result);seen.append(key);return result
        with tempfile.TemporaryDirectory() as folder,patch.object(outline.ev,'call',side_effect=infer),patch.object(outline.ev,'progress'):
            return outline.review_short(None,Path(folder),{'duration_ms':40000},rows,items),seen
    def test_connective_fragment_merges_but_short_independent_story_stays(self):
        items,seen=self.review({'short-S1':'previous'})
        self.assertEqual([s['start'] for s in items],['S0','S2','S3']);self.assertIn('short-S3',seen)
    def test_intro_merges_forward_and_uncertainty_is_visible(self):
        items,_=self.review({'short-S1':'next','short-S3':'uncertain'})
        self.assertEqual([s['start_ms'] for s in items],[0,10000,30000]);self.assertEqual(items[1]['title'],'설명이 이어짐');self.assertTrue(items[-1]['review'])


class ParentTests(unittest.TestCase):
    def group(self,decisions):
        subjects=['요리의 재료','요리의 조리법','컴퓨터 고장 질문','요리 이야기 재개']
        items=[dict(id=f'story-{i}',start_ms=i*1800000,end_ms=(i+1)*1800000,title=t,detail=t) for i,t in enumerate(subjects)]
        def infer(job,folder,key,value,instruction,data,schema,validate):
            index=int(key.rsplit('-',1)[1]);result={'decision':decisions[index-1],'title':subjects[index],'reason':'공통 기준에 따른 판정'}
            validate(result);return result
        with patch.object(outline.ev,'call',side_effect=infer),patch.object(outline.ev,'progress'):
            parents=outline.parents(None,None,items)
        return parents,items

    def test_long_topic_retains_children_and_returned_topic_is_separate(self):
        parents,items=self.group(['same','new','new'])
        self.assertEqual([p['children'] for p in parents],[['story-0','story-1'],['story-2'],['story-3']])
        self.assertEqual(parents[0]['end_ms'],3600000)
        self.assertEqual(len(items),4)

    def test_uncertain_parent_preserves_story_with_review_marker(self):
        parents,items=self.group(['uncertain','new','same'])
        self.assertTrue(parents[0]['review']);self.assertIn('parent_review',items[1])
        self.assertEqual([s for p in parents for s in p['children']],[s['id'] for s in items])
        self.assertEqual(items[1]['parent_id'],parents[0]['id'])


if __name__=='__main__':unittest.main()
