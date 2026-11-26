import copy
import json
import threading
import unittest
from unittest.mock import patch

import game
import server
from players import PlayerError


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.g = game.new_game()
        self.g.update(roles=['村民', '狼人', '预言家', '村民', '狼人', '村民'],
                      alive=[0, 1, 2, 3, 4], phase='talk')
        self.g['notes'][2] = ['2号是狼人']

    def test_speakers_receive_every_previous_speech(self):
        contexts = []

        def respond(seat, messages, **kwargs):
            context = json.loads(messages[-1]['content'])
            contexts.append(context)
            expected = list(range(1, seat + 1))
            self.assertEqual([s['seat'] for s in context['earlier_speeches_today']], expected)
            self.assertNotIn('roles', context)
            self.assertEqual(context['private'], self.g['notes'][seat])
            if context['role'] != '狼人':
                self.assertEqual(context['team'], [])
            return {'speech': f'我是{seat+1}号。' + '我想具体回应前面提出的质疑，并把发言和票型结合起来看。' * 8}

        with patch('game.request_player', side_effect=respond):
            game.advance(self.g, {'speech': '我怀疑2号的立场。'})
        self.assertEqual(len(contexts), 4)
        self.assertEqual(self.g['phase'], 'vote')
        self.assertEqual(len(self.g['speeches']), 5)
        self.assertGreater(len(self.g['speeches'][1]['speech']), 120)

    def test_persona_is_stable_and_legacy_game_loads(self):
        del self.g['personas']
        first = game.view(self.g)
        second = game.view(self.g)
        self.assertEqual(first['seats'], second['seats'])
        self.assertEqual(len({p['id'] for p in self.g['personas'][1:]}), 5)
        self.assertFalse(first['seats'][2]['role'])

    def test_model_failure_rolls_back_entire_round(self):
        original = copy.deepcopy(self.g)
        handler = object.__new__(server.Handler)
        handler.headers = {'Authorization': 'Bearer test-token'}
        replies = []
        handler.reply = lambda status, payload: replies.append((status, payload))
        server.games['test-token'] = (threading.Lock(), self.g)
        with patch('game.request_player', side_effect=[{'speech': '先听发言再看票型。' * 25}, PlayerError('模型暂不可用')]):
            handler.game_request({'revision': 0, 'speech': '请解释。'})
        self.assertEqual(replies[0][0], 502)
        self.assertEqual(self.g, original)
        server.games.pop('test-token')

    def test_bad_action_is_rejected(self):
        with patch('game.request_player', return_value={'target': 99}):
            with self.assertRaises(PlayerError):
                game.decide(self.g, 1, '投票', [0, 2])


if __name__ == '__main__':
    unittest.main()
