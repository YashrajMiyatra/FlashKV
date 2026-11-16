import os
import unittest
from flashkv.server import FlashKVServer


class TestAOFPersistence(unittest.TestCase):
    def setUp(self):
        self.aof_file = "test_flashkv.aof"
        if os.path.exists(self.aof_file):
            os.remove(self.aof_file)

    def tearDown(self):
        if os.path.exists(self.aof_file):
            os.remove(self.aof_file)

    def test_aof_write_and_replay(self):
        # 1. Start server, execute commands, then shutdown
        server1 = FlashKVServer(aof_path=self.aof_file, enable_aof=True)
        server1.execute_command(["SET", "replayed_key", "hello_aof"])
        server1.execute_command(["RPUSH", "replayed_list", "item1", "item2"])
        server1.execute_command(["VADD", "docs", "doc1", "0.1,0.2,0.3"])
        server1.aof.flush()
        server1.aof.close()

        # 2. Start a new server instance with the same AOF file
        server2 = FlashKVServer(aof_path=self.aof_file, enable_aof=True)
        server2.replay_startup()

        # 3. Assert values were recovered
        self.assertEqual(server2.store.get("replayed_key"), "hello_aof")
        self.assertEqual(server2.store.lrange("replayed_list", 0, -1), ["item1", "item2"])
        self.assertIsNotNone(server2.vectors.get("docs"))
        self.assertEqual(len(server2.vectors.get("docs").vectors), 1)

        server2.aof.close()


if __name__ == "__main__":
    unittest.main()
