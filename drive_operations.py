from tkinter import messagebox, filedialog, tk
import ttkbootstrap as ttk
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import os
import io
import mimetypes
import logging
from utils import retry_on_rate_limit
from constants import EXPORT_FORMATS

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DriveOperations:
    def __init__(self, app):
        self.app = app

    @retry_on_rate_limit
    def list_files(self, folder_id='root'):
        if not self.app.service:
            self.app.cache_manager.display_offline_files()
            return
        try:
            self.app.progress.start()
            self.app.tree.delete(*self.app.tree.get_children())
            self.app.file_list.clear()
            self.app.current_folder_id = folder_id
            query = f"'{folder_id}' in parents and trashed=false"
            results = self.app.service.files().list(
                pageSize=1000,
                fields="files(id, name, mimeType, permissions, ownedByMe, size, parents)",
                q=query
            ).execute()
            files = results.get('files', [])
            if not files:
                self.app.update_status("No files or folders found", warning=True)
                return
            for file in files:
                can_delete = file.get('ownedByMe', False)
                for perm in file.get('permissions', []):
                    if perm.get('role') in ['owner', 'writer']:
                        can_delete = True
                        break
                is_folder = file['mimeType'] == 'application/vnd.google-apps.folder'
                display_name = file['name'] + (" (Google Docs)" if file['mimeType'].startswith('application/vnd.google-apps') else "")
                file_type = "Folder" if is_folder else ("Google Docs" if file['mimeType'].startswith('application/vnd.google-apps') else "File")
                permissions = "Editable" if can_delete else "Read-only"
                self.app.file_list[file['name']] = {
                    'id': file['id'],
                    'mimeType': file['mimeType'],
                    'display_name': display_name,
                    'can_delete': can_delete,
                    'type': file_type,
                    'permissions': permissions,
                    'size': file.get('size', 'N/A'),
                    'is_folder': is_folder,
                    'parents': file.get('parents', [])
                }
                self.app.tree.insert("", tk.END, values=(display_name, file_type, permissions))
            self.app.update_status(f"Listed {len(files)} items", success=True)
            self.app.cache_manager.save_offline_cache()
            self.update_breadcrumbs()
        except HttpError as e:
            self.app.update_status(f"Network error: {str(e)}", error=True)
            logging.error(f"List files error: {str(e)}")
        finally:
            self.app.progress.stop()

    def navigate_folder(self, event):
        selected = self.app.tree.selection()
        if not selected:
            return
        display_name = self.app.tree.item(selected[0])['values'][0]
        file_data = next((data for data in self.app.file_list.values() if data['display_name'] == display_name), None)
        if file_data and file_data['is_folder']:
            self.app.folder_stack.append((file_data['display_name'], file_data['id']))
            self.list_files(folder_id=file_data['id'])

    def navigate_to_folder(self, folder_id, folder_name):
        while self.app.folder_stack and self.app.folder_stack[-1][1] != folder_id:
            self.app.folder_stack.pop()
        if not self.app.folder_stack:
            self.app.folder_stack.append(('My Drive', 'root'))
        self.list_files(folder_id=folder_id)
        self.update_breadcrumbs()

    def update_breadcrumbs(self):
        path = " > ".join(name for name, _ in self.app.folder_stack)
        self.app.breadcrumb_label.config(text=path)

    def filter_files(self, *args):
        search_term = self.app.search_var.get().lower()
        self.app.tree.delete(*self.app.tree.get_children())
        for file_name, data in self.app.file_list.items():
            if search_term in file_name.lower() or search_term in data['display_name'].lower():
                self.app.tree.insert("", tk.END, values=(data['display_name'], data['type'], data['permissions']))

    @retry_on_rate_limit
    def upload_file(self):
        try:
            self.app.progress.start()
            file_paths = filedialog.askopenfilenames()
            if not file_paths:
                return
            for file_path in file_paths:
                file_name = os.path.basename(file_path)
                file_metadata = {'name': file_name, 'parents': [self.app.current_folder_id]}
                media = MediaFileUpload(file_path)
                self.app.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                self.app.update_status(f"Uploaded {file_name}", success=True)
            self.list_files(folder_id=self.app.current_folder_id)
            messagebox.showinfo("Success", f"Uploaded {len(file_paths)} file(s)")
        except HttpError as e:
            self.app.update_status(f"Error uploading file: {str(e)}", error=True)
            logging.error(f"Upload error: {str(e)}")
        finally:
            self.app.progress.stop()

    @retry_on_rate_limit
    def create_folder(self):
        try:
            folder_name = tk.simpledialog.askstring("New Folder", "Enter folder name:")
            if not folder_name:
                return
            self.app.progress.start()
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [self.app.current_folder_id]
            }
            self.app.service.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            self.app.update_status(f"Created folder {folder_name}", success=True)
            self.list_files(folder_id=self.app.current_folder_id)
            messagebox.showinfo("Success", f"Created folder {folder_name}")
        except HttpError as e:
            self.app.update_status(f"Error creating folder: {str(e)}", error=True)
            logging.error(f"Create folder error: {str(e)}")
        finally:
            self.app.progress.stop()

    @retry_on_rate_limit
    def download_file(self):
        try:
            self.app.progress.start()
            selected = self.app.tree.selection()
            if not selected:
                self.app.update_status("No files selected", error=True)
                return
            save_dir = filedialog.askdirectory(title="Select Folder to Save Files")
            if not save_dir:
                self.app.update_status("Download cancelled", warning=True)
                return
            downloaded = 0
            for item in selected:
                display_name = self.app.tree.item(item)['values'][0]
                file_data = next((data for data in self.app.file_list.values() if data['display_name'] == display_name), None)
                if not file_data or file_data['is_folder']:
                    continue
                file_id = file_data['id']
                mime_type = file_data['mimeType']
                file_name = next(name for name, data in self.app.file_list.items() if data['display_name'] == display_name)
                if mime_type in EXPORT_FORMATS:
                    export_mime, export_ext, _ = EXPORT_FORMATS[mime_type][0]
                    save_path = os.path.join(save_dir, file_name + export_ext)
                    request = self.app.service.files().export_media(fileId=file_id, mimeType=export_mime)
                else:
                    extension = mimetypes.guess_extension(mime_type) or '.bin'
                    save_path = os.path.join(save_dir, file_name + (extension if not file_name.endswith(extension) else ""))
                    request = self.app.service.files().get_media(fileId=file_id)
                with io.FileIO(save_path, 'wb') as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                downloaded += 1
                self.app.update_status(f"Downloaded {file_name}", success=True)
            self.app.update_status(f"Downloaded {downloaded} file(s)", success=True)
            messagebox.showinfo("Success", f"Downloaded {downloaded} file(s)")
        except HttpError as e:
            self.app.update_status(f"Error downloading files: {str(e)}", error=True)
            logging.error(f"Download error: {str(e)}")
        finally:
            self.app.progress.stop()

    @retry_on_rate_limit
    def delete_file(self):
        try:
            self.app.progress.start()
            selected = self.app.tree.selection()
            if not selected:
                self.app.update_status("No items selected", error=True)
                return
            files_to_delete = []
            file_names = []
            for item in selected:
                display_name = self.app.tree.item(item)['values'][0]
                file_data = next((data for data in self.app.file_list.values() if data['display_name'] == display_name), None)
                if not file_data or not file_data['can_delete']:
                    continue
                files_to_delete.append(file_data['id'])
                file_names.append(next(name for name, data in self.app.file_list.items() if data['display_name'] == display_name))
            if not files_to_delete:
                self.app.update_status("No items can be deleted", warning=True)
                return
            if not messagebox.askyesno("Confirm", f"Delete {len(files_to_delete)} item(s)?"):
                self.app.update_status("Deletion cancelled", warning=True)
                return
            deleted = 0
            for file_id, file_name in zip(files_to_delete, file_names):
                self.app.service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
                deleted += 1
                self.app.update_status(f"Deleted {file_name}", success=True)
            self.list_files(folder_id=self.app.current_folder_id)
            messagebox.showinfo("Success", f"Deleted {deleted} item(s)")
        except HttpError as e:
            self.app.update_status(f"Error deleting items: {str(e)}", error=True)
            logging.error(f"Delete error: {str(e)}")
        finally:
            self.app.progress.stop()

    @retry_on_rate_limit
    def share_file(self):
        try:
            self.app.progress.start()
            selected = self.app.tree.selection()
            if not selected:
                self.app.update_status("No item selected", error=True)
                return
            display_name = self.app.tree.item(selected[0])['values'][0]
            file_data = next((data for data in self.app.file_list.values() if data['display_name'] == display_name), None)
            if not file_data:
                return
            file_id = file_data['id']
            file_name = next(name for name, data in self.app.file_list.items() if data['display_name'] == display_name)
            share_dialog = tk.Toplevel(self.app.root)
            share_dialog.title(f"Share {file_name}")
            share_dialog.geometry("400x300")
            share_dialog.configure(bg=self.app.style.colors.bg)
            text_style = "light" if self.app.is_dark_theme else "dark"
            ttk.Label(share_dialog, text="Share with:", font=("Segoe UI", 10), bootstyle=text_style).pack(pady=10)
            email_var = tk.StringVar()
            ttk.Entry(share_dialog, textvariable=email_var, width=40, bootstyle=text_style).pack(pady=5)
            role_var = tk.StringVar(value="reader")
            ttk.Label(share_dialog, text="Role:", font=("Segoe UI", 10), bootstyle=text_style).pack()
            ttk.Radiobutton(share_dialog, text="Viewer", variable=role_var, value="reader", bootstyle=text_style).pack(anchor="w", padx=20)
            ttk.Radiobutton(share_dialog, text="Editor", variable=role_var, value="writer", bootstyle=text_style).pack(anchor="w", padx=20)
            ttk.Label(share_dialog, text="Shareable Link:", font=("Segoe UI", 10), bootstyle=text_style).pack(pady=10)
            link_var = tk.StringVar()
            ttk.Entry(share_dialog, textvariable=link_var, width=40, state="readonly", bootstyle=text_style).pack(pady=5)
            ttk.Button(share_dialog, text="Generate Link", command=lambda: self.generate_share_link(file_id, link_var), bootstyle=text_style).pack(pady=5)
            def apply_sharing():
                email = email_var.get()
                role = role_var.get()
                if email:
                    permission = {'type': 'user', 'role': role, 'emailAddress': email}
                    self.app.service.permissions().create(fileId=file_id, body=permission, fields='id').execute()
                    self.app.update_status(f"Shared {file_name} with {email}", success=True)
                    share_dialog.destroy()
            ttk.Button(share_dialog, text="Apply", command=apply_sharing, bootstyle=text_style).pack(pady=10)
        except HttpError as e:
            self.app.update_status(f"Error sharing: {str(e)}", error=True)
            logging.error(f"Share error: {str(e)}")
        finally:
            self.app.progress.stop()

    def generate_share_link(self, file_id, link_var):
        try:
            permission = {'type': 'anyone', 'role': 'reader'}
            self.app.service.permissions().create(fileId=file_id, body=permission, fields='id').execute()
            file = self.app.service.files().get(fileId=file_id, fields='webViewLink').execute()
            link_var.set(file.get('webViewLink', ''))
            self.app.update_status("Generated shareable link", success=True)
        except HttpError as e:
            self.app.update_status(f"Error generating link: {str(e)}", error=True)
            logging.error(f"Generate link error: {str(e)}")

    def update_preview(self, event):
        selected = self.app.tree.selection()
        if not selected:
            self.app.preview_label.config(text="Select a file or folder to see details")
            return
        display_name = self.app.tree.item(selected[0])['values'][0]
        file_data = next((data for data in self.app.file_list.values() if data['display_name'] == display_name), None)
        if not file_data:
            self.app.preview_label.config(text="Item data not found")
            return
        file_name = next(name for name, data in self.app.file_list.items() if data['display_name'] == display_name)
        size = file_data['size']
        if size != 'N/A' and not file_data['is_folder']:
            size_bytes = int(size)
            size = f"{size_bytes / (1024 ** 2):.2f} MB" if size_bytes >= 1024 ** 2 else \
                   f"{size_bytes / 1024:.2f} KB" if size_bytes >= 1024 else f"{size_bytes} bytes"
        else:
            size = "N/A"
        preview_text = f"Name: {file_name}\nType: {file_data['type']}\nPermissions: {file_data['permissions']}\nSize: {size}"
        if file_data['is_folder']:
            preview_text += "\nFolder: Contains files and subfolders"
        self.app.preview_label.config(text=preview_text)