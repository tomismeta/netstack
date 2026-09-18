"""Observable collector integrity, deadline and filesystem boundary regressions."""
import json
from pathlib import Path
import signal
import socket
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import netstack_core as core

ADDRESS = '0x' + '11' * 20
TX = '0x' + 'aa' * 32
HASH = '0x' + 'bb' * 32
OTHER_HASH = '0x' + 'cc' * 32


def raw_log(value=1):
    abi = core.load_json('assets/analytics/v2-interface.json')['pair_abi']
    transfer = next(i for i in abi if i.get('name') == 'Transfer')
    return {'address': ADDRESS, 'topics': [core.topic(transfer), '0x' + '00' * 32, '0x' + '00' * 12 + ADDRESS[2:]],
            'data': '0x' + value.to_bytes(32, 'big').hex(), 'blockNumber': '0xa',
            'transactionIndex': '0x0', 'logIndex': '0x0', 'transactionHash': TX,
            'blockHash': HASH, 'removed': False}


class CollectorIntegrity(unittest.TestCase):
    def setUp(self):
        self.ctx = core.Context('lp', deadline=30)
        self.ctx.block = 100
        self.abi = core.load_json('assets/analytics/v2-interface.json')['pair_abi']
        self.responses = []
        self.stub = patch.object(self.ctx, '_exchange_once', side_effect=lambda requests: [self.responses.pop(0) for _ in requests])
        self.stub.start()

    def tearDown(self):
        self.stub.stop()
        self.ctx.close()

    def scan(self, key):
        return list(self.ctx.logs(key, ADDRESS, self.abi, ['Transfer'], 10, 10))

    def test_successful_batch_members_survive_another_members_failure(self):
        specs = [(ADDRESS, self.abi, 'totalSupply', ()),
                 (ADDRESS, self.abi, 'kLast', ()),
                 (ADDRESS, self.abi, 'balanceOf', (ADDRESS,))]
        self.responses.extend(['0x' + (11).to_bytes(32, 'big').hex(),
                               core.RpcError('Historical state unavailable', kind='pruned'),
                               '0x' + (33).to_bytes(32, 'big').hex()])
        with self.assertRaises(core.RpcError):
            self.ctx.calls(specs)
        # No further provider response is available: good members must remain usable.
        self.assertEqual(self.ctx.calls([specs[0], specs[2]]), [11, 33])

    def test_fresh_header_recheck_rejects_changed_cached_block(self):
        self.responses.extend([{'number': '0xa', 'hash': HASH, 'timestamp': '0x64'},
                               {'number': '0xa', 'hash': OTHER_HASH, 'timestamp': '0x64'}])
        self.ctx.header(10)
        with self.assertRaises(core.RpcError):
            self.ctx.header(10, fresh=True)
        self.assertEqual(self.ctx.result['snapshot']['confirmation'], 'invalid')

    def test_independent_scans_reject_conflicting_fork_and_log_contents(self):
        first = raw_log()
        self.responses.extend([[first], [raw_log(2)]])
        self.scan('incoming')
        with self.assertRaises(core.RpcError):
            self.scan('outgoing')
        self.assertFalse(self.ctx.result['coverage']['incoming']['event_coverage_complete'])
        self.assertFalse(self.ctx.result['coverage']['incoming']['snapshot_valid'])

    def test_receipt_cannot_replace_log_with_conflicting_contents(self):
        receipt = {'transactionHash': TX, 'blockHash': HASH, 'blockNumber': '0xa',
                   'transactionIndex': '0x0', 'status': '0x1', 'from': ADDRESS,
                   'to': ADDRESS, 'contractAddress': None, 'logs': [raw_log(2)]}
        self.responses.extend([[raw_log()], receipt])
        self.scan('events')
        with self.assertRaises(core.RpcError):
            self.ctx.receipt(TX)
        self.assertFalse(self.ctx.result['coverage']['events']['event_coverage_complete'])

    def test_identical_overlaps_preserve_each_filter_coverage(self):
        self.responses.extend([[raw_log()], [raw_log()]])
        first, second = self.scan('incoming'), self.scan('outgoing')
        self.assertEqual(first, second)
        self.assertTrue(self.ctx.result['coverage']['incoming']['event_coverage_complete'])
        self.assertTrue(self.ctx.result['coverage']['outgoing']['event_coverage_complete'])

    def test_pristine_planned_scan_can_start_but_completed_scan_cannot_be_replaced(self):
        self.ctx.result['coverage']['planned'] = {'requested_range': [10, 10], 'covered_ranges': [],
            'missing_ranges': [[10, 10]], 'event_coverage_complete': False, 'status': 'not_started'}
        self.responses.append([raw_log()])
        self.scan('planned')
        with self.assertRaises(core.RpcError):
            self.scan('planned')
        self.assertTrue(self.ctx.result['coverage']['planned']['event_coverage_complete'])

    def test_capped_single_block_never_becomes_complete(self):
        self.responses.append([raw_log()] * core.MAX_PAGE_ROWS)
        with self.assertRaises(core.RpcError):
            self.scan('capped')
        self.assertEqual(self.ctx.result['coverage']['capped']['missing_ranges'], [[10, 10]])
        self.assertFalse(self.ctx.result['coverage']['capped']['event_coverage_complete'])


class CollectorBoundaries(unittest.TestCase):
    def test_nonpublic_dns_is_rejected_before_socket_creation(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('127.0.0.1', 443))]
        with patch.object(core.socket, 'getaddrinfo', return_value=answers), \
             patch.object(core.socket, 'socket', side_effect=AssertionError('TCP connection attempted')):
            with self.assertRaises(core.RpcError):
                core._FixedHTTPSConnection(core.RPC_HOST, 443).connect()

    def test_trickling_response_cannot_extend_collector_deadline(self):
        class Trickle:
            status = 200
            def request(self, *args, **kwargs):
                pass
            def getresponse(self):
                return self
            def getheader(self, name, default=None):
                return default
            def read(self, size):
                time.sleep(0.02)
                return b' '
            def close(self):
                pass
        started = time.monotonic()
        ctx = core.Context('lp', deadline=2.2)
        try:
            ctx.result['metrics']['preserved'] = {'supply_raw': '123'}
            ctx.checkpoint()
            with patch.object(core, '_FixedHTTPSConnection', return_value=Trickle()):
                with self.assertRaises(core.StopRun):
                    ctx._rpc('eth_chainId', [])
            self.assertLess(time.monotonic() - started, 1.5)
            self.assertEqual(json.loads(ctx.partial_json('deadline_exhausted'))['metrics']['preserved']['supply_raw'], '123')
        finally:
            ctx.close()

    def test_sigterm_retains_prior_checkpoint_without_more_retrieval(self):
        ctx = core.Context('house', deadline=10)
        try:
            ctx.result['metrics']['queued_raw'] = '4796156268'
            ctx.checkpoint()
            with self.assertRaises(core.StopRun):
                signal.raise_signal(signal.SIGTERM)
            with self.assertRaises(core.StopRun):
                ctx.check()
            document = json.loads(ctx.partial_json('interrupted_by_SIGTERM'))
            self.assertEqual(document['metrics']['queued_raw'], '4796156268')
            self.assertEqual(document['stopping_reason'], 'interrupted_by_SIGTERM')
        finally:
            ctx.close()

    def test_symlink_parent_cannot_redirect_checkpoint_into_package(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            package = base / 'package'
            package.mkdir()
            (base / 'redirect').symlink_to(package, target_is_directory=True)
            with patch.object(core, 'ROOT', package):
                ctx = core.Context('lp', output=base / 'redirect' / 'forbidden-output.json')
                try:
                    with self.assertRaises(core.RpcError):
                        ctx.checkpoint()
                    self.assertFalse((package / 'forbidden-output.json').exists())
                finally:
                    ctx.close()

    def test_parent_rename_cannot_redirect_open_checkpoint_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            package = base / 'package'
            package.mkdir()
            original = base / 'original'
            original.mkdir()
            with patch.object(core, 'ROOT', package):
                ctx = core.Context('lp', output=original / 'result.json')
                try:
                    ctx.result['metrics']['supply_raw'] = '123'
                    ctx.checkpoint()
                    original.rename(base / 'retained')
                    original.symlink_to(package, target_is_directory=True)
                    ctx.result['metrics']['supply_raw'] = '456'
                    try:
                        ctx.checkpoint()
                    except core.RpcError:
                        pass
                    self.assertFalse((package / 'result.json').exists())
                    saved = json.loads((base / 'retained' / 'result.json').read_text())
                    self.assertIn(saved['metrics']['supply_raw'], ('123', '456'))
                finally:
                    ctx.close()


if __name__ == '__main__':
    unittest.main()
