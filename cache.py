import pickle
import logging
from constants import CACHE_FILE

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CacheManager:
    def __init__(self, app):
        self.app = app

    def load_offline_cache(self):
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, 'rb') as f:
                    self.app.offline_cache = pickle.load(f)
                self.app.update_status("Loaded offline cache", success=True)
                if not self.app.service:
                    self.app.display_offline_files()
            except Exception as e:
                logging.error(f"Failed to load cache: {str(e)}")
                self.app.update_status("Failed to load offline cache", warning=True)

    def save_offline_cache(self):
        try:
            with open(CACHE_FILE, 'wb') as f:
                pickle.dump(self.app.file_list, f)
            self.app.update_status("Saved offline cache", success=True)
        except Exception as e:
            logging.error(f"Failed to save cache: {str(e)}")
            self.app.update_status("Failed to save offline cache", warning=True)

    def display_offline_files(self):
        self.app.tree.delete(*self.app.tree.get_children())
        for file_name, data in self.app.offline_cache.items():
            self.app.tree.insert("", tk.END, values=(data['display_name'], data['type'], data['permissions']))
        self.app.update_status("Showing offline cached files (read-only)", warning=True)