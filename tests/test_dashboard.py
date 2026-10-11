"""Check dashboard selection, future reveal, sample mode, and local HTTP access."""
import copy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from repackq.classical.trials import synthetic_pool
from repackq.dashboard.service import DashboardService
from repackq.dashboard.server import make_handler


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.service = DashboardService(self.temporary.name)

    def test_clean_checkout_is_explicit_sample_without_scientific_evidence(self):
        bootstrap = self.service.bootstrap()
        self.assertEqual(bootstrap['source'], 'synthetic-fixture')
        self.assertIsNone(bootstrap['evaluation'])
        self.assertIsNone(bootstrap['benchmark'])
        trial = self.service.create_trial({})
        self.assertEqual(len(trial['results']), 4)
        self.assertEqual(trial['settings']['partition'], 'all')
        self.assertEqual(trial['quantum']['executed_runs'], 0)
        self.assertEqual(trial['quantum']['runs'], [])
        self.assertIn(trial['quantum']['status'], ('not_run', 'not_installed'))
        self.assertFalse(trial['future_available'])
        with self.assertRaisesRegex(ValueError, 'no recorded'):
            self.service.reveal(trial['trial_id'])

    def test_measurements_are_revealed_only_after_selection(self):
        cells, _, metadata = synthetic_pool()
        truth = {c.cell_id: {'actual_capacity_ah':1.5+i*.03, 'target_cycle_index':200,
                            'nearest_cycle_distance':0} for i,c in enumerate(cells)}
        self.service.synthetic = False
        with patch('repackq.dashboard.service.history_pool', return_value=(cells,truth,metadata)):
            trial = self.service.create_trial({})
        token = trial['trial_id']
        # neither the initial response nor the solver export may expose future values
        self.assertNotIn('truth', trial)
        self.assertNotIn('actual_capacity_ah', json.dumps(trial))
        self.assertNotIn('actual_capacity_ah', json.dumps(self.service.export_problem(token)))
        self.assertTrue(all(r['observed_pack_divergence'] is None for r in trial['results']))
        indices = trial['results'][0]['selected_indices']
        manual = self.service.manual(token,indices)
        self.assertIsNone(manual['observed_pack_divergence'])
        revealed = self.service.reveal(token)
        self.assertEqual(revealed['truth'], truth)
        self.assertTrue(all(r['observed_pack_divergence'] is not None for r in revealed['results']))
        self.assertIsNotNone(self.service.manual(token,indices)['observed_pack_divergence'])
        changed = copy.deepcopy(truth)
        for row in changed.values(): row['actual_capacity_ah'] *= .7
        with patch('repackq.dashboard.service.history_pool', return_value=(cells,changed,metadata)):
            other = self.service.create_trial({})
        self.assertEqual(trial['snapshots'],other['snapshots'])
        self.assertEqual([r['selected_indices'] for r in trial['results']],
                         [r['selected_indices'] for r in other['results']])

    def test_invalid_settings_manual_groups_and_expired_trials(self):
        for payload in ({'seed':-1},{'seed':True},{'horizon':201},{'mode':'fake'}, {'truth':{}}, {'candidates':True}, {'quantum':'yes'}, {'partition':'train'}):
            with self.assertRaises(ValueError): self.service.create_trial(payload)
        with self.assertRaises(ValueError): self.service.create_trial({'horizon':50})
        with self.assertRaisesRegex(ValueError, 'no real training or test'):
            self.service.create_trial({'partition':'test'})
        trial = self.service.create_trial({})
        for indices in ([0,1],[0,0,1,2],[0,1,2,99]):
            with self.assertRaises(ValueError): self.service.manual(trial['trial_id'],indices)
        with self.assertRaisesRegex(ValueError,'expired'): self.service.reveal('missing')

    def test_real_dashboard_defaults_to_full_inventory_and_preserves_optional_test_scope(self):
        class FakeModel:
            artifact = {'cell_splits': {'train':[str(i) for i in range(60)],
                        'validation':[str(i) for i in range(60,72)], 'test':[str(i) for i in range(72,86)]}}
            def predict(self, primary, second, **kwargs):
                return {'current_capacity_ah':2, 'predicted_capacity_ah':1.7,
                        'prediction_uncertainty_ah':.06}
        self.service.synthetic = False
        self.service.model = FakeModel()
        self.service.data = {'cells':[{'cell_id':str(i),
                            'primary':[{'cycle':c,'capacity_ah':2} for c in range(4)],
                            'second_life':[{'cycle':200,'capacity_ah':1.6}]} for i in range(86)]}
        full = self.service.create_trial({})
        self.assertEqual(full['metadata']['eligible_cells'],86)
        self.assertEqual(full['settings']['partition'],'all')
        self.assertEqual(len(full['snapshots']),8)
        self.assertGreater(full['metadata']['candidate_partitions']['train'],0)
        self.assertEqual(self.service.bootstrap()['dataset_cells'],86)
        self.assertNotIn('actual_capacity_ah',json.dumps(full))
        exported = self.service.export_problem(full['trial_id'])
        self.assertEqual(exported['metadata'],full['metadata'])
        self.assertNotIn('actual_capacity_ah',json.dumps(exported))
        held_out = self.service.create_trial({'partition':'test'})
        self.assertEqual(held_out['metadata']['eligible_cells'],14)
        self.assertTrue(all(int(c['cell_id'])>=72 for c in held_out['snapshots']))
        self.assertEqual(self.service.bootstrap()['defaults']['partition'],'all')

    def test_present_but_mismatched_assets_fail_instead_of_sample(self):
        # use a small model fixture with the wrong dataset hash
        from repackq.prediction.features import FEATURE_NAMES
        root = Path(self.temporary.name)
        (root/'models').mkdir(); (root/'data/processed').mkdir(parents=True)
        (root/'data/processed/cell_histories.json').write_text('{"cells":[]}')
        artifact = {'schema_version':1, 'feature_names':FEATURE_NAMES,
            'preprocessing':{key:{'median':0,'mean':0,'scale':1} for key in FEATURE_NAMES},
            'weights':[[[0] for _ in range(len(FEATURE_NAMES)+1)]], 'output_scale_ah':3,
            'validation_residual_rmse_ah':.1, 'training_data_sha256':'wrong',
            'domain':{'cutoff_max':100,'horizon_min':50,'horizon_max':200}}
        (root/'models/capacity_model.json').write_text(json.dumps(artifact))
        with self.assertRaisesRegex(ValueError,'checksum'): DashboardService(root)


class HTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(DashboardService(cls.temporary.name)))
        cls.thread = Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_address[1]}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(); cls.temporary.cleanup()

    def request(self,path,payload=None,headers=None):
        data = json.dumps(payload).encode() if payload is not None else None
        return urlopen(Request(self.url+path,data=data,headers=headers or {}),timeout=5)

    def test_assets_and_round_trip(self):
        for path,content_type in (('/','text/html'),('/app.js','text/javascript'),('/styles.css','text/css'),('/favicon.svg','image/svg+xml')):
            with self.request(path) as response:
                self.assertEqual(response.status,200)
                self.assertIn(content_type,response.headers['Content-Type'])
                self.assertTrue(response.read())
        with self.request('/api/bootstrap') as response:
            self.assertEqual(json.load(response)['source'],'synthetic-fixture')
        with self.request('/api/trial',{}) as response:
            trial=json.load(response)
        with self.request('/api/manual',{'trial_id':trial['trial_id'],'indices':[0,1,2,3]}) as response:
            self.assertIsNone(json.load(response)['observed_pack_divergence'])
        with self.request('/api/problem?trial_id='+trial['trial_id']) as response:
            exported=json.load(response)
            self.assertIn('qubo',exported)
            self.assertNotIn('truth',exported)

    def test_unknown_files_and_cross_origin_mutations_rejected(self):
        for path in ('/models/capacity_model.json','/../README.md','/api/not-found'):
            with self.assertRaises(HTTPError) as error: self.request(path)
            self.assertEqual(error.exception.code,404)
        with self.assertRaises(HTTPError) as error:
            self.request('/api/trial',{}, {'Origin':'https://example.com'})
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:
            self.request('/api/bootstrap',headers={'Host':'example.com'})
        self.assertEqual(error.exception.code,403)
        with self.assertRaises(HTTPError) as error:
            self.request('/api/trial',[])
        self.assertEqual(error.exception.code,400)


if __name__ == '__main__': unittest.main()
