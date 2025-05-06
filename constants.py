from pathlib import Path

# Constants
CACHE_FILE = Path.home() / '.quickdrive_cache.pkl'
SCOPES = ['https://www.googleapis.com/auth/drive']
EXPORT_FORMATS = {
    'application/vnd.google-apps.document': [
        ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx', 'Microsoft Word'),
        ('application/pdf', '.pdf', 'PDF')
    ],
    'application/vnd.google-apps.spreadsheet': [
        ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', '.xlsx', 'Microsoft Excel'),
        ('application/pdf', '.pdf', 'PDF')
    ],
    'application/vnd.google-apps.presentation': [
        ('application/vnd.openxmlformats-officedocument.presentationml.presentation', '.pptx', 'Microsoft PowerPoint'),
        ('application/pdf', '.pdf', 'PDF')
    ]
}