import unittest
from dataclasses import replace
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rcln import rate_content, rate_file, rate_notes
from rcln.engine import _hold_support, _ln_share, _rc_weight
from spm_rating import rate_notes as upstream, load_model
from spm_rating.api import align
from spm_rating import engine


def objects_chart(keys, objects):
    lines = ['osu file format v14', '[General]', 'Mode:3', '[Difficulty]',
             f'CircleSize:{keys}', 'OverallDifficulty:7', '[HitObjects]']
    for t, col, duration in objects:
        x = int((col + .5)*512/keys)
        lines.append(f'{x},192,{t},128,0,{t+duration}:0:0:0:0:' if duration
                     else f'{x},192,{t},1,0,0:0:0:0:')
    return '\n'.join(lines)


def chart(keys, kind):
    return objects_chart(keys, [(1000+150*i, i % keys,
                         370 if kind == 'ln' or (kind == 'mixed' and i % 5 == 0) else 0)
                         for i in range(60)])


def sections(hold_fraction):
    """Matched two-head patterns; tap sections are denser than hold sections."""
    t = 1000
    objects = []
    for index in range(60):
        hold = index < round(60*hold_fraction)
        step = 116 if hold else 43
        for i in range(12):
            lane = i % 3
            for c in (lane,6-lane):
                objects.append((t+i*step,c,round(2.2*step) if hold else 0))
        t += 12*step+270
    return objects


class Scores(unittest.TestCase):
    def test_upstream_and_supported_modes(self):
        for model in ('detail', 'compact', 'detail-4k'):
            for keys in (4, 6, 7):
                for kind in ('tap', 'ln', 'mixed'):
                    with self.subTest(model=model, keys=keys, kind=kind):
                        notes = engine.parser.parse_content(chart(keys, kind), rate=1.25)
                        got = rate_notes(notes, model)
                        self.assertAlmostEqual(got['spm'], upstream(notes, model)['score'], places=10)
                        if kind == 'tap': self.assertEqual(got['rc'], got['spm'])
                        if kind == 'ln':
                            tap = replace(notes, is_ln=np.zeros(notes.n_notes, bool), ln_end=notes.time.copy())
                            self.assertLess(abs(got['rc']-upstream(tap, model)['score']), .005)
                        mirror = rate_notes(engine.mirror(notes), model)
                        for key in ('spm', 'rc', 'ln'):
                            self.assertAlmostEqual(got[key], mirror[key], places=9)
                        self.assertEqual(got['ln_coverage'], mirror['ln_coverage'])
                        self.assertGreaterEqual(got['ln_coverage'], 0.)
                        self.assertLessEqual(got['ln_coverage'], 1.)
                        if kind == 'tap':
                            self.assertEqual(got['ln_coverage'], 0.)
                            self.assertEqual(got['ln'], 0.)

    def test_fractional_time_and_scales(self):
        notes = engine.parser.parse_content(chart(7, 'mixed'))
        shift = np.where(notes.col % 2, .35, .7)
        notes = replace(notes, time=notes.time+shift, ln_end=np.where(notes.is_ln, notes.ln_end+shift, notes.ln_end))
        for name in ('detail', 'compact', 'detail-4k'):
            with self.subTest(model=name):
                model = load_model(name)
                got = rate_notes(notes, model, scale='reference')
                self.assertAlmostEqual(got['spm'], upstream(notes, model, scale='reference')['score'], places=10)
                raw = rate_notes(notes, model)
                for key in ('spm', 'rc', 'ln'):
                    self.assertAlmostEqual(got[key], align(model.alignment['7'], raw[key]), places=10)
                self.assertEqual(got['ln_coverage'], raw['ln_coverage'])
                self.assertEqual(got['ln_coverage'], rate_notes(engine.mirror(notes), model)['ln_coverage'])
                self.assertEqual(set(got), {'spm','rc','ln','ln_coverage','key_count','rate','scale',
                                            'model','model_identity','heads'})
                self.assertEqual(got['model_identity'], model.identity)

    def test_input_and_cancel(self):
        with self.assertRaises(ValueError): rate_content(chart(5, 'tap'))
        with self.assertRaises(ValueError): rate_content(chart(7, 'tap'), rate=0)
        with self.assertRaises(ValueError): rate_file('not-read.osu', rate=-1)
        with self.assertRaises(InterruptedError): rate_content(chart(7, 'tap'), cancel=lambda: True)
        notes = engine.parser.parse_content(chart(7, 'tap'))
        with self.assertRaises(ValueError): rate_notes(replace(notes, rate=float('nan')))
        with self.assertRaises(ValueError): rate_notes(notes, scale='unknown')
        with self.assertRaises(ValueError): rate_notes(notes, replace(load_model('detail'), revision=1))
        polls = iter((False, False, True))
        with self.assertRaises(InterruptedError): rate_notes(notes, cancel=lambda: next(polls))

    def test_local_share_and_clean_head_weight(self):
        share = _ln_share(np.array([0., 1., 2., 0.]), np.array([2., 2., 2., 0.]), 1.)
        self.assertEqual(share[0], 0.)
        self.assertGreater(share[2], share[1])
        self.assertEqual(share[3], 0.)
        time = np.array([0., 100., 200., 2000.])
        weight = _rc_weight(time, np.array([0., .9, 0., 0.]), np.array([0., .9, 0., 0.]), 250., .2)
        self.assertGreater(weight[0], weight[1])
        self.assertAlmostEqual(weight[0], weight[2])
        self.assertEqual(weight[-1], 1.)
        np.testing.assert_equal(_rc_weight(time, np.zeros(4), np.zeros(4), 250., .2), np.ones(4))

    def test_hold_support_prefers_sustained_over_short_holds(self):
        notes = engine.parser.parse_content(chart(7, 'ln'))
        short = replace(notes, ln_end=notes.time+20.)
        q = notes.time[15:45]
        self.assertTrue(np.all(_hold_support(notes, q, 600., 80.) > _hold_support(short, q, 600., 80.)))

    def test_low_pressure_decoration(self):
        objects = sections(0.)
        end = max(t for t,_,_ in objects)+900
        heads = [(end+450*i, 4+i % 3, 0) for i in range(200)]
        control = rate_content(objects_chart(7, objects+heads))
        decorated = rate_content(objects_chart(7, objects+[(t,c,100) for t,c,_ in heads]))
        self.assertLessEqual(abs(decorated['spm']-control['spm']), .15)
        self.assertLess(decorated['ln'], .20*decorated['spm'])
        self.assertLessEqual(decorated['rc'], decorated['spm'])

    def test_hard_tap_section_can_exceed_whole_chart_spm(self):
        got = rate_content(objects_chart(7, sections(.80)))
        self.assertGreater(got['rc'], got['spm'])

    def test_static_hold_uses_upstream_support_row(self):
        chart_text = chart(4, 'ln').split('[HitObjects]')[0] + (
            '[HitObjects]\n64,192,1000,128,0,3000:0:0:0:0:\n'
            '192,192,1000,128,0,3000:0:0:0:0:')
        notes = engine.parser.parse_content(chart_text)
        got = rate_notes(notes)
        self.assertAlmostEqual(got['spm'], upstream(notes, 'detail')['score'], places=10)
        self.assertGreater(got['ln'], 0.)
        self.assertTrue(np.isfinite(got['rc']))

if __name__ == '__main__': unittest.main()
