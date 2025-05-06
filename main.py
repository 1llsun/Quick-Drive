import tkinter as tk
import platform
from gui import QuickDriveApp

def main():
    root = tk.Tk()
    if platform.system() in ['Darwin', 'Linux']:
        root.option_add('*Font', 'Helvetica 10')
    app = QuickDriveApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()