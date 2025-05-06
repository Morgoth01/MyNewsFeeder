__app__  = "My News Feeder"
__author__  = "Morgoth01"
__version__ = "0.1.0"


import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog, font
import urllib.request
from urllib.error import HTTPError, URLError
import xml.etree.ElementTree as ET
import json
import webbrowser
import html
import threading
import re
import os
import sys
from datetime import datetime
import time
import gzip
import io

def resource_path(rel_path):
    if getattr(sys, 'frozen', False):
        # PyInstaller bundles into a temp folder _MEIPASS
        base = sys._MEIPASS
    else:
        base = os.path.dirname(__file__)
    return os.path.join(base, rel_path)

# Paths for persistence
APPDATA_PATH = os.path.join(os.getenv('APPDATA'), 'MyNewsFeeder')
os.makedirs(APPDATA_PATH, exist_ok=True)
FEED_FILE = os.path.join(APPDATA_PATH, 'feeds.json')
SETTINGS_FILE = os.path.join(APPDATA_PATH, 'settings.json')

# Default settings
DEFAULT_SETTINGS = {
    'dark_mode': False,
    'auto_refresh': False,
    'layout_mode': 'vertical',
    'max_items': 10,
    'keyword': '',
    'font_size': 12,
    'tree_width': 150,
    'refresh_interval': 60
}

# Load settings
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        for k, v in DEFAULT_SETTINGS.items():
            settings.setdefault(k, v)
        return settings
    return DEFAULT_SETTINGS.copy()

SETTINGS = load_settings()

# Load feeds
def load_feeds():
    if os.path.exists(FEED_FILE):
        with open(FEED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

FEEDS = load_feeds()

class FeedManager(simpledialog.Dialog):
    """Dialog for managing RSS/Atom feeds."""
    def __init__(self, parent):
        self.parent = parent
        self.feeds = [f.copy() for f in FEEDS]
        super().__init__(parent, title='Manage Feeds')

    def buttonbox(self):
        pass

    def body(self, frame):
        dark = self.parent.dark_mode.get()
        bg = '#2e2e2e' if dark else 'white'
        fg = '#dddddd' if dark else 'black'
        sel_bg = '#555555' if dark else 'lightblue'
        style = ttk.Style()
        style.theme_use('clam')
        # Style for ttk widgets
        for w in ['TFrame','TLabel','TButton','TCheckbutton','TSpinbox','TEntry','TMenubutton']:
            style.configure(w, background=bg, foreground=fg)
            style.map(w, background=[('active', bg)], foreground=[('active', fg)])
        frame.configure(background=bg)

        cols = [('enabled','Enabled',50), ('name','Name',150), ('url','URL',SETTINGS['tree_width'])]
        for i, (c, txt, wdt) in enumerate(cols):
             ttk.Label(frame, text=txt, background=bg, foreground=fg)

        self.tree = ttk.Treeview(frame, columns=[c for c,_,__ in cols], show='headings', height=12)
        for c,_,wdt in cols:
            self.tree.heading(c, text=c.title())
            self.tree.column(c, width=wdt, anchor='center' if c=='enabled' else 'w',stretch=True)
            self.tree.grid(row=1, column=0, columnspan=3, sticky='nsew')
        frame.rowconfigure(1, weight=1)
        self._refresh()

        bar = ttk.Frame(frame)
        bar.grid(row=2, column=0, columnspan=3, pady=5)
        ttk.Button(bar, text='Add', command=self._add).pack(side='left', padx=5)
        ttk.Button(bar, text='Edit', command=self._edit).pack(side='left', padx=5)
        ttk.Button(bar, text='Remove', command=self._remove).pack(side='left', padx=5)
        ttk.Button(bar, text='Toggle', command=self._toggle).pack(side='left', padx=5)
        mb = ttk.Menubutton(bar, text='Advanced ▾')
        # Context menu styling
        menu = tk.Menu(mb, tearoff=False, background=bg, foreground=fg,
                       activebackground=sel_bg, activeforeground=fg)
        mb['menu'] = menu
        menu.add_command(label='Sort A–Z', command=self._sort_az)
        menu.add_command(label='Sort Z–A', command=self._sort_za)
        menu.add_separator()
        menu.add_command(label='Move Up', command=self._move_up)
        menu.add_command(label='Move Down', command=self._move_down)
        menu.add_separator()
        menu.add_command(label='Import…', command=self._import)
        menu.add_command(label='Export…', command=self._export)
        mb.pack(side='left', padx=5)
        ttk.Button(bar, text='OK', command=self.ok).pack(side='left', padx=20)
        ttk.Button(bar, text='Cancel', command=self.cancel).pack(side='left', padx=5)
        return frame

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for f in self.feeds:
            mark = '✔' if f.get('enabled', True) else ''
            self.tree.insert('', 'end', values=(mark, f['name'], f['url']))

    def _add(self):
        name = simpledialog.askstring('Feed Name','Enter name:', parent=self)
        url  = simpledialog.askstring('Feed URL','Enter URL:',  parent=self)
        if name and url:
            self.feeds.append({'name':name,'url':url,'enabled':True})
            self._refresh(); self._save()

    def _edit(self):
        sel = self.tree.selection()
        if not sel: return
        i = self.tree.index(sel[0]); f = self.feeds[i]
        nm = simpledialog.askstring('Edit Name','Modify name:',initialvalue=f['name'],parent=self)
        ur = simpledialog.askstring('Edit URL','Modify URL:', initialvalue=f['url'], parent=self)
        if nm and ur:
            f['name'], f['url'] = nm, ur
            self._refresh(); self._save()

    def _remove(self):
        sel = self.tree.selection()
        if sel:
            del self.feeds[self.tree.index(sel[0])]
            self._refresh(); self._save()

    def _toggle(self):
        sel = self.tree.selection()
        if sel:
            f = self.feeds[self.tree.index(sel[0])]
            f['enabled'] = not f['enabled']
            self._refresh(); self._save()

    def _sort_az(self):   self.feeds.sort(key=lambda x:x['name'].lower());          self._refresh(); self._save()
    def _sort_za(self):   self.feeds.sort(key=lambda x:x['name'].lower(), reverse=True); self._refresh(); self._save()
    def _move_up(self):   self._move(-1)
    def _move_down(self): self._move(1)
    def _move(self,d):
        sel = self.tree.selection()
        if sel:
            i = self.tree.index(sel[0]); j = i + d
            if 0 <= j < len(self.feeds):
                self.feeds[i], self.feeds[j] = self.feeds[j], self.feeds[i]
                self._refresh()
                self.tree.selection_set(self.tree.get_children()[j])
                self._save()

    def _import(self):
        fn = filedialog.askopenfilename(filetypes=[('JSON','*.json')])
        if fn:
            with open(fn,'r',encoding='utf-8') as f:
                self.feeds = json.load(f)
            self._refresh(); self._save()

    def _export(self):
        fn = filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('JSON','*.json')])
        if fn:
            with open(fn,'w',encoding='utf-8') as f:
                json.dump(self.feeds,f,indent=2)

    def _save(self):
        global FEEDS
        FEEDS = [f.copy() for f in self.feeds]
        with open(FEED_FILE,'w',encoding='utf-8') as f:
            json.dump(FEEDS,f,indent=2)

class NewsViewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('My News Feeder')
        self.geometry('1000x700')
        icon = tk.PhotoImage(file=resource_path('mynewsfeeder.png'))
        self.iconphoto(True, icon)
        self.dark_mode        = tk.BooleanVar(value=SETTINGS['dark_mode'])
        self.auto_refresh     = tk.BooleanVar(value=SETTINGS['auto_refresh'])
        self.refresh_interval = tk.IntVar(value=SETTINGS['refresh_interval'])
        self.layout_mode      = tk.StringVar(value=SETTINGS['layout_mode'])
        self.max_items        = tk.IntVar(value=SETTINGS['max_items'])
        self.keyword          = tk.StringVar(value=SETTINGS['keyword'])
        self.font_size        = tk.IntVar(value=SETTINGS['font_size'])
        self.detail_font      = font.Font(size=self.font_size.get())
        self.current_articles = []
        self.current_link     = None

        self._build_ui()
        self._apply_theme()
        self.update_layout()
        self._start_auto_refresh()

    def _build_ui(self):
        self.toolbar = ttk.Frame(self)
        self.toolbar.pack(fill='x', padx=10, pady=5)
        ttk.Button(self.toolbar, text='Manage Feeds', command=self._manage_feeds).pack(side='left', padx=5)
        help_mb = ttk.Menubutton(self.toolbar, text='Help ▾', style='Help.TMenubutton')
        self.help_menu = tk.Menu(help_mb, tearoff=False)
        help_mb['menu'] = self.help_menu
        self.help_menu.add_command(label='GitHub', command=lambda: webbrowser.open('https://github.com/Morgoth01/MyNewsFeeder?tab=readme-ov-file'))
        self.help_menu.add_command(label='Check for updates', command=lambda: webbrowser.open('https://github.com/Morgoth01/MyNewsFeeder/releases'))
        self.help_menu.add_command(label='About', command=self._show_about)
        help_mb.pack(side='left', padx=5)
        ttk.Label(self.toolbar, text='Keyword:').pack(side='left', padx=5)
        self.key_entry = ttk.Entry(self.toolbar, textvariable=self.keyword, width=20)
        self.key_entry.pack(side='left', padx=5)
        ttk.Button(self.toolbar, text='Refresh', command=self.update_layout).pack(side='left', padx=5)
        mb = ttk.Menubutton(self.toolbar, text='Options ▾')
        m = tk.Menu(mb, tearoff=False)
        mb['menu'] = m
        m.add_checkbutton(label='Dark Mode', variable=self.dark_mode, command=self._apply_theme)
        m.add_checkbutton(label='Auto Refresh', variable=self.auto_refresh)
        m.add_separator()
        m.add_command(label='Max items...', command=lambda: self._prompt_int('Max items', self.max_items, 1, 100, self.update_layout))
        m.add_command(label='Font size...', command=lambda: self._prompt_int('Font size', self.font_size, 8, 32, self._apply_font_size))
        m.add_command(label='Refresh interval...', command=lambda: self._prompt_int('Refresh interval', self.refresh_interval, 10, 3600, self.update_layout))
        m.add_separator()
        lm = tk.Menu(m, tearoff=False)
        lm.add_radiobutton(label='Vertical', variable=self.layout_mode, value='vertical',   command=self._toggle_layout)
        lm.add_radiobutton(label='Horizontal', variable=self.layout_mode, value='horizontal', command=self._toggle_layout)
        m.add_cascade(label='Layout', menu=lm)
        mb.pack(side='left', padx=5)
        self._build_pane()

    def _show_about(self):
        messagebox.showinfo(
        'About',
        f'{__app__ }\nVersion {__version__}\nAuthor: {__author__}'
    )

    def _prompt_int(self, title, var, lo, hi, cb=lambda:None):
        v = simpledialog.askinteger(title, f'Enter {title.lower()}:', initialvalue=var.get(), minvalue=lo, maxvalue=hi, parent=self)
        if v is not None:
            var.set(v)
            cb()

    def _build_pane(self):
        if hasattr(self, 'pw'):
            self.pw.destroy()
        orient = tk.VERTICAL if self.layout_mode.get() == 'horizontal' else tk.HORIZONTAL
        self.pw = ttk.Panedwindow(self, orient=orient)
        self.pw.pack(fill='both', expand=True, padx=10, pady=10)
        left = ttk.Frame(self)
        self.pw.add(left, weight=1)
        w = SETTINGS.get('tree_width', 150)
        self.tree = ttk.Treeview(left, show='tree')
        self.tree.column('#0', width=w)
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', self._on_select)
        self.tree.bind('<Configure>', self._save_width)
        right = ttk.Frame(self)
        self.pw.add(right, weight=2)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.detail = tk.Text(right, wrap='word', state='disabled', font=self.detail_font)
        self.detail.grid(row=0, column=0, sticky='nsew')
        self.open_btn = ttk.Button(right, text='Open Link', command=self._open_link)
        self.open_btn.grid(row=1, column=0, sticky='ew', pady=5)

    def _save_width(self, event=None):
        SETTINGS['tree_width'] = self.tree.winfo_width()
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(SETTINGS, f, indent=2)

    def _apply_theme(self):
        dark = self.dark_mode.get()
        bg = '#2e2e2e' if dark else 'white'
        fg = '#dddddd' if dark else 'black'
        self.configure(bg=bg)
        style = ttk.Style()
        style.theme_use('clam')
        for w in ['TFrame','TLabel','TCheckbutton','TButton','TEntry','Spinbox','TMenubutton']:
            style.configure(w, background=bg, foreground=fg)
            style.map(w, background=[('active',bg)], foreground=[('active',fg)])

        # Hover effect for all buttons
        style.map('TButton',
            background=[('active', '#444444')],
            foreground=[('active', '#ffffff')]
        )
        style.map('TMenubutton',
            background=[('active', '#444444')],
            foreground=[('active', '#ffffff')]
        )

        # Specific Menubutton styles
        style.configure('Options.TMenubutton', background=bg, foreground=fg)
        style.map('Options.TMenubutton', background=[('active',bg)], foreground=[('active',fg)])
        style.configure('Help.TMenubutton', background=bg, foreground=fg)
        style.map('Help.TMenubutton',
             background=[('active','#444444')],
             foreground=[('active','#ffffff')]
        )
        style.configure('Treeview', background=bg, fieldbackground=bg, foreground=fg)
        style.map('Treeview', background=[('selected','gray')], foreground=[('selected',fg)])
        self.detail.configure(background=bg, foreground=fg, insertbackground=fg)
        style.configure('TEntry',fieldbackground=bg, background=bg, foreground=fg)
        style.map('TEntry',fieldbackground=[('!disabled', bg)], foreground=[('!disabled', fg)])

    def _apply_font_size(self):
        sz = self.font_size.get()
        SETTINGS['font_size'] = sz
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(SETTINGS, f, indent=2)
        self.detail_font.configure(size=sz)
        self.detail.configure(font=self.detail_font)

    def _toggle_layout(self):
        new = 'vertical' if self.layout_mode.get() == 'vertical' else 'horizontal'
        self.layout_mode.set(new)
        SETTINGS['layout_mode'] = new
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(SETTINGS, f, indent=2)
        self._build_pane()
        self.update_layout()

    def _manage_feeds(self):
        FeedManager(self)
        self.update_layout()

    def _fetch_articles(self):
        arts = []
        kw = self.keyword.get().lower()
        mx = self.max_items.get()
        for f in FEEDS:
            if not f.get('enabled', True):
                continue
            url = f['url']
            try:
                # Reddit support
                if 'reddit.com' in url and url.endswith('.rss'):
                    sub = re.search(r'/r/([^/]+)/', url)
                    if sub:
                        api = f"https://www.reddit.com/r/{sub.group(1)}/new.json?limit={mx}"
                        req = urllib.request.Request(api, headers={'User-Agent':'Mozilla/5.0'})
                        data = urllib.request.urlopen(req, timeout=10).read().decode()
                        for p in json.loads(data)['data']['children']:
                            d = p['data']
                            t = d.get('title','')
                            txt = re.sub(r'<[^>]+>', '', d.get('selftext','')).strip()
                            if kw and kw not in t.lower() and kw not in txt.lower():
                                continue
                            link = d.get('url','')
                            pub = datetime.fromtimestamp(d.get('created_utc',0)).strftime('%Y-%m-%d %H:%M:%S')
                            arts.append({'feed':f['name'],'title':t,'desc':html.unescape(txt),'link':link,'pub':pub})
                        continue
                # Standard RSS/Atom
                req = urllib.request.Request(url, headers={
                    'User-Agent':'Mozilla/5.0',
                    'Accept':'application/rss+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Encoding':'gzip'
                })
                resp = urllib.request.urlopen(req, timeout=10)
                raw = resp.read()
                data = gzip.GzipFile(fileobj=io.BytesIO(raw)).read() if resp.getheader('Content-Encoding','').lower()=='gzip' else raw
                root = ET.fromstring(data)
                items = root.findall('.//item') or root.findall('.//entry')
                cnt = 0
                for it in items:
                    t = it.findtext('title') or ''
                    desc = it.findtext('description') or it.findtext('summary') or ''
                    pubd = it.findtext('pubDate') or it.findtext('updated') or ''
                    try:
                        dt = datetime.fromisoformat(pubd.replace('Z','+00:00'))
                        pub = dt.astimezone().strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pub = pubd
                    txt = re.sub(r'<[^>]+>', '', desc).strip()
                    if kw and kw not in t.lower() and kw not in txt.lower():
                        continue
                    link = it.findtext('link') or it.find('{http://www.w3.org/2005/Atom}link').attrib.get('href','')
                    arts.append({'feed':f['name'],'title':t,'desc':html.unescape(txt),'link':link,'pub':pub})
                    cnt += 1
                    if cnt >= mx:
                        break
            except HTTPError as e:
                # Retry on 403 with alt UA
                if e.code == 403:
                    try:
                        alt_req = urllib.request.Request(url, headers={
                            'User-Agent':'Mozilla/5.0 (compatible; MyNewsFeeder/1.0)',
                            'Accept':'application/rss+xml,application/xml;q=0.9,*/*;q=0.8'
                        })
                        alt_resp = urllib.request.urlopen(alt_req, timeout=10)
                        alt_raw = alt_resp.read()
                        alt_data = gzip.GzipFile(fileobj=io.BytesIO(alt_raw)).read() if alt_resp.getheader('Content-Encoding','').lower()=='gzip' else alt_raw
                        alt_root = ET.fromstring(alt_data)
                        alt_items = alt_root.findall('.//item') or alt_root.findall('.//entry')
                        cnt2 = 0
                        for it2 in alt_items:
                            t2 = it2.findtext('title') or ''
                            desc2 = it2.findtext('description') or it2.findtext('summary') or ''
                            pubd2 = it2.findtext('pubDate') or it2.findtext('updated') or ''
                            try:
                                dt2 = datetime.fromisoformat(pubd2.replace('Z','+00:00'))
                                pub2 = dt2.astimezone().strftime('%Y-%m-%d %H:%M:%S')
                            except:
                                pub2 = pubd2
                            txt2 = re.sub(r'<[^>]+>', '', desc2).strip()
                            if kw and kw not in t2.lower() and kw not in txt2.lower():
                                continue
                            link2 = it2.findtext('link') or it2.find('{http://www.w3.org/2005/Atom}link').attrib.get('href','')
                            arts.append({'feed':f['name'],'title':t2,'desc':html.unescape(txt2),'link':link2,'pub':pub2})
                            cnt2 += 1
                            if cnt2 >= mx:
                                break
                        continue
                    except Exception:
                        arts.append({'feed':f['name'],'title':'[ERROR] HTTP 403 Forbidden','desc':'','link':'','pub':''})
                        continue
                arts.append({'feed':f['name'],'title':f'[ERROR] HTTP {e.code}','desc':'','link':'','pub':''})
            except URLError as e:
                arts.append({'feed':f['name'],'title':f'[ERROR] URL {e.reason}','desc':'','link':'','pub':''})
            except Exception as e:
                arts.append({'feed':f['name'],'title':f'[ERROR] {e}','desc':'','link':'','pub':''})
        return arts

    def update_layout(self, *args):
        SETTINGS.update({
            'dark_mode':    self.dark_mode.get(),
            'auto_refresh': self.auto_refresh.get(),
            'layout_mode':  self.layout_mode.get(),
            'max_items':    self.max_items.get(),
            'keyword':      self.keyword.get(),
            'font_size':    self.font_size.get(),
            'refresh_interval': self.refresh_interval.get()
        })
        try:
            SETTINGS['tree_width'] = self.tree.column('#0')['width']
        except:
            pass
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(SETTINGS, f, indent=2)
        self._apply_theme()
        threading.Thread(target=self._async, daemon=True).start()

    def _async(self):
        self.current_articles = self._fetch_articles()
        self.after(0, self._populate_tree)

    def _populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        groups = {f['name']: [] for f in FEEDS if f.get('enabled', True)}
        for i, art in enumerate(self.current_articles):
            groups.setdefault(art['feed'], []).append((i, art))
        for name, items in groups.items():
            pid = self.tree.insert('', 'end', text=name, open=True)
            for idx, a in items:
                self.tree.insert(pid, 'end', iid=str(idx), text=a['title'])

    def _on_select(self, event=None):
        sel = self.tree.selection()
        if not sel or not sel[0].isdigit():
            return
        art = self.current_articles[int(sel[0])]
        details = f"Feed: {art['feed']}\nTitle: {art['title']}\nPublished: {art['pub']}\n\n{art['desc']}"
        self.detail.config(state='normal')
        self.detail.delete('1.0', 'end')
        self.detail.insert('end', details)
        self.detail.config(state='disabled')
        self.current_link = art['link']

    def _open_link(self):
        if self.current_link:
            webbrowser.open(self.current_link, new=2)

    def _start_auto_refresh(self):
        def loop():
            while True:
                if self.auto_refresh.get():
                    self.update_layout()
                time.sleep(self.refresh_interval.get())
        threading.Thread(target=loop, daemon=True).start()

if __name__ == '__main__':
    NewsViewer().mainloop()