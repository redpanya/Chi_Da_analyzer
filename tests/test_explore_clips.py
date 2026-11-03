import unittest
from unittest.mock import patch
from pathlib import Path
from archive import explore_clips


class ClipTimeline(unittest.TestCase):
    def read(self,state,result,selection=None):
        with patch('archive.context_job.state',return_value=state), patch('archive.context_job.result',return_value=result) as load:
            value=explore_clips.read(Path('/unused'),'1',10000,selection)
            return value,load

    def test_selected_local_external_and_partial(self):
        runs=[{'id':'a','mode':'clips','label':'외부 AI'},{'id':'b','mode':'clips','label':'Gemma'}, {'id':'c','mode':'detail'}]
        result={'complete':False,'stale':True,'items':[{'id':'one','start_ms':1000,'end_ms':2000,'title':'장면'}]}
        state={'runs':runs,'clip_run':'a'}
        value,load=self.read(state,result);self.assertEqual(value['run'],'a');self.assertEqual(len(value['items']),1)
        self.assertTrue(any('일부 처리' in n for n in value['notes']));self.assertTrue(any('지난 입력' in n for n in value['notes']))
        value,load=self.read(state,result,'b');self.assertEqual(load.call_args.args[-1],'b')
        value,load=self.read({'runs':runs,'clip_run':'missing'},result);self.assertEqual(value['run'],'b')

    def test_bad_rows_and_missing_results_do_not_break_timeline(self):
        result={'complete':True,'items':[{'start_ms':a,'end_ms':b} for a,b in [(0,500),(10000,10001),(-1,100),(True,500),(500,400),(0,float('nan'))]]}
        value,_=self.read({'runs':[{'id':'a','mode':'clips'}]},result)
        self.assertEqual(len(value['items']),1);self.assertTrue(any('5개 제외' in n for n in value['notes']))
        value,load=self.read({'runs':[]},result);self.assertEqual(value['items'],[]);load.assert_not_called()
        value,load=self.read({'runs':[{'id':'a','mode':'clips'}]},result,'deleted');self.assertEqual(value['items'],[]);load.assert_not_called()
        with patch('archive.context_job.state',side_effect=ValueError('손상')):
            self.assertEqual(explore_clips.read(Path('/unused'),'1',10000)['items'],[])


if __name__=='__main__':unittest.main()
