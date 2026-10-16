"""Resume the frozen recovery while preserving provider JSON order on cached calls."""
import json
from pathlib import Path

import run_pipeline_v2_recovery as recovery
from pipeline_api import encoded

BASE_CLIENT = recovery.RecoveryClient


def provider_order(result, record):
    if record.get('status') != 'ok' or encoded(result) != encoded(record['result']):
        raise ValueError('Cached result differs from its saved successful record')
    if record.get('cost_basis') == 'offline_validation_recovery':
        return result
    original = json.loads(record['provider_response']['choices'][0]['message']['content'])
    if encoded(original) != encoded(result):
        raise ValueError('Provider JSON differs from the saved result')
    return original


class ReplayClient(BASE_CLIENT):
    def __init__(self, config, root, out, **kwargs):
        super().__init__(config, root, out, **kwargs)
        receipt = {'adapter_source_sha256':recovery.v2.sha(Path(__file__)),
                   'config_sha256':self.config_sha256,
                   'policy':'Replay original provider JSON key order only after structural equality; retain offline-normalised results as saved.',
                   'model_settings_unchanged':True,'paid_replays':False}
        path = Path(out)/'replay_adapter_receipt.json'
        if path.exists():
            if recovery.v2.read(path,{}) != receipt:
                raise ValueError('Replay adapter receipt changed')
        else:
            recovery.v2.save(path,receipt)

    def generate(self, job_id, *args, **kwargs):
        result = super().generate(job_id, *args, **kwargs)
        record = self.logical_records['v2long:'+job_id[len('v2full:'):]]
        # Embedded prompt JSON must retain the original provider order across restarts.
        return provider_order(result,record)


def main():
    previous = recovery.RecoveryClient
    try:
        recovery.RecoveryClient = ReplayClient
        recovery.main()
    finally:
        recovery.RecoveryClient = previous


if __name__ == '__main__':
    main()
