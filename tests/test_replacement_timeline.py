import random
import threading
import unittest
from unittest.mock import patch

from archive import replacement_timeline as timeline
from archive.storage import Conflict


class TimelineTests(unittest.TestCase):
    def compare(self,old,new,base=None):
        return timeline.compare('old','new',old,new,base or old,threading.Event())

    def test_match_finds_earlier_audio_and_rejects_ambiguous_signals(self):
        rng=random.Random(5)
        old=[rng.random()*4 for _ in range(400)]
        self.assertAlmostEqual(timeline.offset(old,[0]*200+old+[0]*400),-2.)
        self.assertIsNone(timeline.offset(old,old+[0]*200+old))
        self.assertIsNone(timeline.offset([0]*400,[0]*1000))

    def test_extra_margin_requires_stable_sound_at_all_three_locations(self):
        with patch.object(timeline,'envelope',return_value=[]),patch.object(timeline,'offset',side_effect=[-1.9,-2.,-1.95]):
            self.assertAlmostEqual(self.compare(10800,10797)['new_minus_old_seconds'],-1.95)
        for values in [[-2.,0.,-1.95], [1.,None,None], [5.8,5.8,5.8]]:
            with self.subTest(values=values),patch.object(timeline,'envelope',return_value=[]),patch.object(timeline,'offset',side_effect=values):
                with self.assertRaises(Conflict):self.compare(10800,10797)

    def test_short_clip_large_difference_and_baseline_guard(self):
        with patch.object(timeline,'envelope',side_effect=AssertionError('음성 검사가 필요하지 않은 길이')):
            self.assertEqual(self.compare(3600,3598),{})
            for old,new,base in [(60,57,60),(20000,19994,20000),(19000,18999,19005)]:
                with self.assertRaises(Conflict):self.compare(old,new,base)
