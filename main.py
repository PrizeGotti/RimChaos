import tkinter as tk
from tkinter import ttk, messagebox
import twitchio
from twitchio.ext import commands
import random
import json
import os
import asyncio
import threading
import time
import sys

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS2
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

CONFIG_FILE = resource_path("config.json")

class RimChaosBot(commands.Bot):
    def __init__(self, token, channel, gui):
        super().__init__(token=token, prefix='!', initial_channels=[channel])
        self.gui = gui
        self.votes = {}
        self.current_events = []
        self.used_events = []
        self.voting_active = False
        self.vote_counts = {1: 0, 2: 0, 3: 0, 4: 0}

    async def event_ready(self):
        print(f'Connected to Twitch as {self.nick}')

    async def event_message(self, message):
        if message.echo:
            return

        if self.voting_active and message.content.isdigit():
            vote = int(message.content)
            if 1 <= vote <= 4:
                if message.author.name in self.votes:
                    old_vote = self.votes[message.author.name]
                    self.vote_counts[old_vote] -= 1
                self.votes[message.author.name] = vote
                self.vote_counts[vote] += 1
                self.gui.update_vote_display()

class RimChaos:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("RimWorld Chaos Mod")
        self.root.geometry("800x600")

        icon_path = resource_path("rimchaos.ico")  # Place your .ico file in the same directory
        self.root.iconbitmap(icon_path)
        
        # Define colors
        self.GREEN_BG = '#00FF00'
        self.BLACK_BG = '#000000'  # Bright green for keying
        
        # Configure styles for the UI
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Vote.Horizontal.TProgressbar", foreground='red', background='red', troughcolor='black')
        
        # Set window background
        self.root.configure(bg=self.GREEN_BG)
        
        self.events = self.load_events()
        self.disabled_events = set()
        self.bot = None
        
        self.setup_gui()
        self.load_credentials()

    def load_events(self):
        try:
            with open(resource_path('events.txt'), 'r') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            messagebox.showerror("Error", "events.txt not found!")
            return []

    def setup_gui(self):
        # Login Frame - starts hidden
        self.login_frame = ttk.LabelFrame(self.root, text="Twitch Login")
        self.login_frame.pack(padx=10, pady=5, fill="x")
        self.login_frame.pack_forget()

        ttk.Label(self.login_frame, text="Username:").grid(row=0, column=0, padx=5, pady=5)
        self.username_var = tk.StringVar()
        self.username_entry = ttk.Entry(self.login_frame, textvariable=self.username_var)
        self.username_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(self.login_frame, text="OAuth Token:").grid(row=1, column=0, padx=5, pady=5)
        self.oauth_var = tk.StringVar()
        self.oauth_entry = ttk.Entry(self.login_frame, textvariable=self.oauth_var, show="*")
        self.oauth_entry.grid(row=1, column=1, padx=5, pady=5)

        self.save_credentials_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.login_frame, text="Save Credentials", 
                       variable=self.save_credentials_var).grid(row=2, column=0, columnspan=2)

        ttk.Button(self.login_frame, text="Connect", command=self.connect_to_twitch).grid(
            row=3, column=0, columnspan=2, pady=5)

        # Mouse enter/leave bindings
        self.root.bind('<Enter>', self.show_login)
        self.root.bind('<Leave>', self.hide_login)

        # Events Frame
        self.events_frame = tk.Frame(self.root, bg=self.GREEN_BG)
        self.events_frame.pack(padx=10, pady=5, fill="both", expand=True)
        
        self.event_frames = []
        self.event_labels = []
        self.progress_bars = []
        self.vote_labels = []
        
        for i in range(4):
            frame = tk.Frame(self.events_frame, bg=self.GREEN_BG)
            frame.pack(fill="x", padx=5, pady=2)
            self.event_frames.append(frame)
            
            # Event label with green background
            event_label = tk.Label(frame, text="", bg=self.BLACK_BG, fg='white', height=2, font='Helvetica 14 bold', anchor="w")
            event_label.pack(side="left", fill="x", pady=5, expand=True)
            self.event_labels.append(event_label)
            
            # Progress bar with black background and red fill, matching label height
            progress = ttk.Progressbar(frame, length=390, mode='determinate', 
                                     style='Vote.Horizontal.TProgressbar')
            progress.pack(side="right", pady=5, fill="y")
            self.progress_bars.append(progress)
            
            # Vote count label with green background
            vote_label = tk.Label(frame, text="0", bg=self.BLACK_BG, fg='white', height=2, font='Helvetica 14 bold')
            vote_label.pack(side="right", pady=5)
            self.vote_labels.append(vote_label)

        self.timer_label = tk.Label(self.events_frame, text="Time remaining: --", 
                                  bg=self.BLACK_BG, fg='white', height=2, font='Helvetica 14 bold')
        self.timer_label.pack(padx=5, pady=5, fill="x")

        # Options Button
        self.options_button = ttk.Button(self.root, text="Event Options", 
                                       command=self.show_options)
        self.options_button.pack(pady=5)
        self.options_button.pack_forget()

    def show_login(self, event):
        self.login_frame.pack(padx=10, pady=5, fill="x")
        self.options_button.pack(pady=5)

    def hide_login(self, event):
        if not self.is_mouse_in_login():
            self.login_frame.pack_forget()
            self.options_button.pack_forget()

    def is_mouse_in_login(self):
        x = self.root.winfo_pointerx() - self.root.winfo_rootx()
        y = self.root.winfo_pointery() - self.root.winfo_rooty()
        login_bbox = self.login_frame.bbox()
        if login_bbox:
            return (login_bbox[0] <= x <= login_bbox[2] and 
                    login_bbox[1] <= y <= login_bbox[3])
        return False

    def show_options(self):
        options_window = tk.Toplevel(self.root)
        options_window.title("Event Options")
        options_window.geometry("300x400")

        # Create main container frame
        container = ttk.Frame(options_window)
        container.pack(fill="both", expand=True)

        # Create canvas with scrollbar
        canvas = tk.Canvas(container, width=280)  # Set specific width for canvas
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        
        # Configure canvas
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Create frame for content
        scrollable_frame = ttk.Frame(canvas)
        
        # Pack scrollbar and canvas
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        # Create window inside canvas with fixed width
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=260)

        # Add the checkboxes
        for event in self.events:
            var = tk.BooleanVar(value=event not in self.disabled_events)
            cb = ttk.Checkbutton(scrollable_frame, text=event, variable=var,
                               command=lambda e=event, v=var: self.toggle_event(e, v))
            cb.pack(anchor="w", padx=5, pady=2, fill="x")

        # Update scrollregion after adding all checkboxes
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    def toggle_event(self, event, var):
        if var.get():
            self.disabled_events.discard(event)
        else:
            self.disabled_events.add(event)

    def load_credentials(self):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                self.username_var.set(config.get('username', ''))
                self.oauth_var.set(config.get('oauth', ''))
        except FileNotFoundError:
            pass

    def save_credentials(self):
        if self.save_credentials_var.get():
            config = {
                'username': self.username_var.get(),
                'oauth': self.oauth_var.get()
            }
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f)

    def connect_to_twitch(self):
        username = self.username_var.get()
        oauth = self.oauth_var.get()
        
        if not username or not oauth:
            messagebox.showerror("Error", "Please enter both username and OAuth token!")
            return

        self.save_credentials()
        self.bot = RimChaosBot(token=oauth, channel=username, gui=self)
        
        bot_thread = threading.Thread(target=self.run_bot)
        bot_thread.daemon = True
        bot_thread.start()

        self.start_voting()

    def run_bot(self):
        self.bot.run()

    def start_voting(self):
        available_events = [e for e in self.events if e not in self.bot.used_events 
                          and e not in self.disabled_events]
        
        if len(available_events) < 4:
            self.bot.used_events = []
            available_events = [e for e in self.events if e not in self.disabled_events]

        self.bot.current_events = random.sample(available_events, 4)
        for i, event in enumerate(self.bot.current_events):
            self.event_labels[i].config(text=f"{i+1}. {event}")
            self.vote_labels[i].config(text="0")
            self.progress_bars[i]['value'] = 0

        self.bot.voting_active = True
        self.bot.votes.clear()
        self.bot.vote_counts = {1: 0, 2: 0, 3: 0, 4: 0}

        self.countdown(60)

    def update_vote_display(self):
        total_votes = sum(self.bot.vote_counts.values())
        if total_votes > 0:
            for i in range(4):
                votes = self.bot.vote_counts[i+1]
                percentage = (votes / total_votes) * 100
                self.progress_bars[i]['value'] = percentage
                self.vote_labels[i].config(text=str(votes))

    def countdown(self, remaining):
        if remaining <= 0:
            self.end_voting()
            return

        self.timer_label.config(text=f"Time remaining: {remaining}")
        self.root.after(1000, self.countdown, remaining - 1)

    def end_voting(self):
        self.bot.voting_active = False
        max_votes = max(self.bot.vote_counts.values())
        winning_options = [k for k, v in self.bot.vote_counts.items() if v == max_votes]
        winner = random.choice(winning_options)
        winning_event = self.bot.current_events[winner-1]

        asyncio.run_coroutine_threadsafe(
            self.bot.connected_channels[0].send(f"!buy {winning_event}"),
            self.bot.loop
        )

        self.bot.used_events.append(winning_event)
        if len(self.bot.used_events) > 10:
            self.bot.used_events.pop(0)

        self.root.after(5000, self.start_voting)

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = RimChaos()
    app.run()
