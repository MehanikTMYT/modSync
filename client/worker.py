class SyncWorker:
    def __init__(self, api):
        self.api = api

    def run(self, mods_path, log):
        for msg in self.api.sync_mods(mods_path):
            log(msg)
