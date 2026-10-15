"""Historical inspection never interrupts independently publishing source data."""
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.replay import install_replay
from simulators.producer import SyntheticProducer, publish_batch, require_paused_sources


@pytest.mark.parametrize('source', [
    'ride_scada', 'ticketing', 'vision', 'cmms', 'erp', 'workforce',
    'bms', 'water', 'weather', 'gis',
])
def test_external_acquisition_continues_while_recorded_view_is_immutable(tmp_path, source):
    app = create_app(str(tmp_path / 'park.db'), run_background=False)
    install_replay(app, str(tmp_path / 'replay.db'), record_background=False, probe_renderer=False)
    with TestClient(app) as client:
        assert client.post(f'/api/connectors/{source}/simulation', json={'mode':'paused'}).status_code == 200
        require_paused_sources(client, [source])
        producer = SyntheticProducer([source], 'heatwave')
        first = producer.batches(1)[source]
        assert publish_batch(client, source, first)['accepted'] == len(first['events'])
        timeline = client.get('/api/timeline').json()['snapshots']
        ident = timeline[0]['id']
        recorded = client.post('/api/view', json={'mode':'replay', 'snapshot_id':ident}).json()
        second = producer.batches(2)[source]
        assert publish_batch(client, source, second)['accepted'] == len(second['events'])
        assert publish_batch(client, source, second)['duplicates'] == len(second['events'])
        current = client.get(f'/api/connectors/{source}/snapshot').json()
        assert {row['event_id'] for row in current['observations']} == {row['event_id'] for row in second['events']}
        historical = client.get('/api/view/state').json()
        for key in ('assets', 'kpis', 'accepted_state_revision', 'timestamp'):
            assert historical[key] == recorded[key]
        newer = client.get('/api/timeline').json()['snapshots']
        assert len(newer) > len(timeline)
        assert client.post(f'/api/connectors/{source}/simulation', json={'mode':'live'}).status_code == 409
        assert client.post('/api/actions', json={'action':'reset'}).status_code == 409
        # Source validation still applies; replay cannot turn arbitrary writes into events.
        assert client.post(f'/api/connectors/{source}/ingest', json={}).status_code == 422
        live = client.post('/api/view', json={'mode':'live'}).json()
        assert live['accepted_state_revision'] != recorded['accepted_state_revision']
        assert live['accepted_state_revision'] == client.get('/api/state').json()['accepted_state_revision']
