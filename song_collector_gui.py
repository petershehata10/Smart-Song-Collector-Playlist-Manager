from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple
import os
import json
import random
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


# ========== DATA MODEL ==========

@dataclass
class Song:
    """Represents a single song in the collection."""
    title: str
    artist: str
    duration_seconds: int
    genre: str
    rating: int  # 1–5
    filepath: str = ""      # path to audio file (optional)
    cover_path: str = ""    # path to album image (PNG preferred)
    id: int = field(default_factory=int)

    def __post_init__(self) -> None:
        if self.duration_seconds < 0:
            raise ValueError("Duration must be non-negative.")
        if not (1 <= self.rating <= 5):
            raise ValueError("Rating must be between 1 and 5.")

    @property
    def duration_minutes(self) -> float:
        return self.duration_seconds / 60.0

    def similarity_score(self, keyword: str) -> float:
        """
        'Clever' algorithm:
        Computes how similar a keyword is to title+artist using words.
        Score 0..1 (higher = more similar).
        """
        kw_words = set(keyword.lower().split())
        text = f"{self.title} {self.artist}".lower()
        song_words = set(text.split())

        if not kw_words or not song_words:
            return 0.0

        common = kw_words & song_words
        union = kw_words | song_words
        return len(common) / len(union)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "artist": self.artist,
            "duration_seconds": self.duration_seconds,
            "genre": self.genre,
            "rating": self.rating,
            "filepath": self.filepath,
            "cover_path": self.cover_path,
            "id": self.id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Song":
        return cls(
            title=data["title"],
            artist=data["artist"],
            duration_seconds=data["duration_seconds"],
            genre=data["genre"],
            rating=data["rating"],
            filepath=data.get("filepath", ""),
            cover_path=data.get("cover_path", ""),
            id=data.get("id", 0),
        )


class SongCollector:
    """Stores all songs and provides operations over them."""

    def __init__(self) -> None:
        self._songs: List[Song] = []
        self._next_id: int = 1

    # ----- CRUD -----
    def add_song(
        self,
        title: str,
        artist: str,
        duration_seconds: int,
        genre: str,
        rating: int,
        filepath: str,
        cover_path: str,
    ) -> Song:
        song = Song(
            id=self._next_id,
            title=title,
            artist=artist,
            duration_seconds=duration_seconds,
            genre=genre,
            rating=rating,
            filepath=filepath,
            cover_path=cover_path,
        )
        self._songs.append(song)
        self._next_id += 1
        return song

    def remove_song_by_id(self, song_id: int) -> bool:
        for s in self._songs:
            if s.id == song_id:
                self._songs.remove(s)
                return True
        return False

    def get_song_by_id(self, song_id: int) -> Song | None:
        for s in self._songs:
            if s.id == song_id:
                return s
        return None

    def list_songs(self) -> List[Song]:
        return list(self._songs)

    def update_song(
        self,
        song_id: int,
        *,
        title: str,
        artist: str,
        duration_seconds: int,
        genre: str,
        rating: int,
        filepath: str,
        cover_path: str,
    ) -> bool:
        """
        Update properties of an existing song.
        Returns True on success, False if song_id not found.
        """
        song = self.get_song_by_id(song_id)
        if song is None:
            return False
        song.title = title
        song.artist = artist
        song.duration_seconds = duration_seconds
        song.genre = genre
        song.rating = rating
        song.filepath = filepath
        song.cover_path = cover_path
        return True

    # ----- sorting -----
    def sort_songs(self, key: str) -> None:
        if key == "Title":
            self._songs.sort(key=lambda s: s.title.lower())
        elif key == "Duration":
            self._songs.sort(key=lambda s: s.duration_seconds)
        elif key == "Rating":
            self._songs.sort(key=lambda s: s.rating, reverse=True)
        elif key == "Newest":
            self._songs.sort(key=lambda s: s.id, reverse=True)
        elif key == "Oldest":
            self._songs.sort(key=lambda s: s.id)

    # ----- searching -----
    def search_smart(self, keyword: str) -> List[Song]:
        scored: List[Tuple[Song, float]] = [
            (s, s.similarity_score(keyword)) for s in self._songs
        ]
        scored = [(s, score) for s, score in scored if score > 0.0]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [s for s, _ in scored]

    # ----- statistics -----
    def genre_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for s in self._songs:
            counts[s.genre] = counts.get(s.genre, 0) + 1
        return counts

    def total_duration(self, songs: List[Song] | None = None) -> int:
        if songs is None:
            songs = self._songs
        return sum(s.duration_seconds for s in songs)

    # ----- save / load -----
    def save_to_file(self, filename: str) -> None:
        data = {
            "next_id": self._next_id,
            "songs": [s.to_dict() for s in self._songs],
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_file(self, filename: str) -> None:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._songs = [Song.from_dict(d) for d in data.get("songs", [])]
        max_id = max((s.id for s in self._songs), default=0)
        self._next_id = max(max_id + 1, int(data.get("next_id", max_id + 1)))


# ========== GUI APPLICATION ==========

class SongCollectorApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Song Collector & Playlist Manager")
        self.root.geometry("1300x700")
        self.root.minsize(1200, 650)

        self.dark_mode = False
        self.cover_image: tk.PhotoImage | None = None
        self.current_edit_id: int | None = None

        self._configure_style()
        self.collector = SongCollector()
        self._create_widgets()
        self._apply_theme_to_runtime_widgets()

    # ------- visual style --------
    def _configure_style(self) -> None:
        self._bg_light = "#f3f3f3"
        self._fg_light = "#000000"
        self._entry_bg_light = "#ffffff"

        self._bg_dark = "#1e1e1e"
        self._fg_dark = "#ffffff"
        self._entry_bg_dark = "#2b2b2b"

        self._accent = "#0078D7"

        bg = self._bg_dark if self.dark_mode else self._bg_light
        fg = self._fg_dark if self.dark_mode else self._fg_light
        entry_bg = self._entry_bg_dark if self.dark_mode else self._entry_bg_light

        self.root.configure(bg=bg)
        style = ttk.Style(self.root)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=bg)
        style.configure("TLabelframe", background=bg)
        style.configure(
            "TLabelframe.Label",
            background=bg,
            foreground=fg,
            font=("Segoe UI", 11, "bold"),
        )
        style.configure(
            "TLabel",
            background=bg,
            foreground=fg,
            font=("Segoe UI", 10),
        )
        style.configure(
            "TButton",
            font=("Segoe UI", 10),
            padding=6,
        )
        style.configure(
            "TEntry",
            font=("Segoe UI", 10),
            fieldbackground=entry_bg,
            foreground=fg,
        )
        style.configure(
            "TCombobox",
            font=("Segoe UI", 10),
            fieldbackground=entry_bg,
            foreground=fg,
        )
        style.map(
            "TButton",
            background=[("active", self._accent)],
            foreground=[("active", "#ffffff")],
        )

    def toggle_theme(self) -> None:
        self.dark_mode = not self.dark_mode
        self._configure_style()
        self._apply_theme_to_runtime_widgets()

    def _apply_theme_to_runtime_widgets(self) -> None:
        bg = self._bg_dark if self.dark_mode else self._bg_light
        fg = self._fg_dark if self.dark_mode else self._fg_light
        entry_bg = self._entry_bg_dark if self.dark_mode else self._entry_bg_light

        self.root.configure(bg=bg)
        if hasattr(self, "lst_songs"):
            self.lst_songs.configure(
                bg=entry_bg,
                fg=fg,
                selectbackground=self._accent,
                selectforeground="#ffffff",
            )
        if hasattr(self, "lbl_cover"):
            self.lbl_cover.configure(background=bg)

    def _create_widgets(self) -> None:
        # --- input frame ---
        frm_input = ttk.LabelFrame(self.root, text="Add / Edit Song")
        frm_input.grid(row=0, column=0, padx=12, pady=10, sticky="new")

        ttk.Label(frm_input, text="Title:").grid(row=0, column=0, sticky="w")
        ttk.Label(frm_input, text="Artist:").grid(row=1, column=0, sticky="w")
        ttk.Label(frm_input, text="Duration (sec):").grid(row=2, column=0, sticky="w")
        ttk.Label(frm_input, text="Genre:").grid(row=3, column=0, sticky="w")
        ttk.Label(frm_input, text="Rating (1–5):").grid(row=4, column=0, sticky="w")
        ttk.Label(frm_input, text="Audio file:").grid(row=5, column=0, sticky="w")
        ttk.Label(frm_input, text="Cover image:").grid(row=6, column=0, sticky="w")

        self.var_title = tk.StringVar()
        self.var_artist = tk.StringVar()
        self.var_duration = tk.StringVar()
        self.var_genre = tk.StringVar()
        self.var_rating = tk.StringVar()
        self.var_filepath = tk.StringVar()
        self.var_coverpath = tk.StringVar()

        entry_width = 32

        ttk.Entry(frm_input, textvariable=self.var_title,
                  width=entry_width).grid(row=0, column=1, padx=5, pady=3, sticky="ew")
        ttk.Entry(frm_input, textvariable=self.var_artist,
                  width=entry_width).grid(row=1, column=1, padx=5, pady=3, sticky="ew")
        ttk.Entry(frm_input, textvariable=self.var_duration,
                  width=entry_width).grid(row=2, column=1, padx=5, pady=3, sticky="ew")
        ttk.Entry(frm_input, textvariable=self.var_genre,
                  width=entry_width).grid(row=3, column=1, padx=5, pady=3, sticky="ew")
        ttk.Entry(frm_input, textvariable=self.var_rating,
                  width=entry_width).grid(row=4, column=1, padx=5, pady=3, sticky="ew")

        file_frame = ttk.Frame(frm_input)
        file_frame.grid(row=5, column=1, padx=5, pady=3, sticky="ew")
        ttk.Entry(file_frame, textvariable=self.var_filepath,
                  width=entry_width - 8).grid(row=0, column=0, sticky="ew")
        ttk.Button(file_frame, text="Browse…",
                   command=self.browse_audio).grid(row=0, column=1, padx=4)

        cover_frame = ttk.Frame(frm_input)
        cover_frame.grid(row=6, column=1, padx=5, pady=3, sticky="ew")
        ttk.Entry(cover_frame, textvariable=self.var_coverpath,
                  width=entry_width - 8).grid(row=0, column=0, sticky="ew")
        ttk.Button(cover_frame, text="Browse PNG…",
                   command=self.browse_cover).grid(row=0, column=1, padx=4)

        btn_frame = ttk.Frame(frm_input)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=10, sticky="ew")
        ttk.Button(btn_frame, text="Add song",
                   command=self.add_song).grid(row=0, column=0, sticky="ew", padx=2)
        ttk.Button(btn_frame, text="Update selected",
                   command=self.update_selected_song).grid(row=0, column=1, sticky="ew", padx=2)
        ttk.Button(btn_frame, text="Clear form",
                   command=self.clear_form).grid(row=0, column=2, sticky="ew", padx=2)
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)

        # --- search / sort / stats frame ---
        frm_actions = ttk.LabelFrame(self.root, text="Search / Sort / Stats")
        frm_actions.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="new")

        ttk.Label(frm_actions, text="Search keyword:").grid(row=0, column=0, sticky="w")
        self.var_search = tk.StringVar()
        ttk.Entry(frm_actions, textvariable=self.var_search, width=20).grid(
            row=0, column=1, padx=5, pady=3, sticky="w"
        )
        ttk.Button(frm_actions, text="Smart search",
                   command=self.smart_search).grid(row=0, column=2, padx=5)

        ttk.Label(frm_actions, text="Sort by:").grid(row=1, column=0, sticky="w")
        self.var_sort = tk.StringVar(value="Title")
        cmb_sort = ttk.Combobox(
            frm_actions,
            textvariable=self.var_sort,
            values=["Title", "Duration", "Rating", "Newest", "Oldest"],
            width=18,
            state="readonly",
        )
        cmb_sort.grid(row=1, column=1, padx=5, pady=3, sticky="w")
        ttk.Button(frm_actions, text="Apply sort",
                   command=self.apply_sort).grid(row=1, column=2, padx=5)

        ttk.Button(frm_actions, text="Show genre stats",
                   command=self.show_stats).grid(row=2, column=0, columnspan=3, pady=4, sticky="ew")

        ttk.Button(frm_actions, text="Toggle dark / light",
                   command=self.toggle_theme).grid(row=3, column=0, pady=6, sticky="ew")
        ttk.Button(frm_actions, text="Save library",
                   command=self.save_library).grid(row=3, column=1, pady=6, sticky="ew")
        ttk.Button(frm_actions, text="Load library",
                   command=self.load_library).grid(row=3, column=2, pady=6, sticky="ew")

        # --- list frame ---
        frm_list = ttk.LabelFrame(self.root, text="Songs")
        frm_list.grid(row=0, column=1, rowspan=2,
                      padx=(5, 12), pady=10, sticky="nsew")

        self.lst_songs = tk.Listbox(
            frm_list,
            width=70,
            height=20,
            font=("Segoe UI", 10),
            selectmode=tk.EXTENDED,
        )
        self.lst_songs.grid(row=0, column=0, columnspan=4,
                            padx=5, pady=5, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            frm_list, orient="vertical", command=self.lst_songs.yview
        )
        scrollbar.grid(row=0, column=4, sticky="ns")
        self.lst_songs.configure(yscrollcommand=scrollbar.set)

        self.lbl_cover = ttk.Label(frm_list, text="Album cover preview\n(PNG)")
        self.lbl_cover.grid(row=0, column=5, padx=10, pady=5, sticky="n")
        self.lst_songs.bind("<<ListboxSelect>>", self.on_song_selected)

        ttk.Button(frm_list, text="Play selected",
                   command=self.play_selected).grid(row=1, column=0, pady=6, padx=3, sticky="ew")
        ttk.Button(frm_list, text="Play ALL",
                   command=self.play_all).grid(row=1, column=1, pady=6, padx=3, sticky="ew")
        ttk.Button(frm_list, text="Play random",
                   command=self.play_random).grid(row=1, column=2, pady=6, padx=3, sticky="ew")
        ttk.Button(frm_list, text="Delete selected",
                   command=self.delete_selected).grid(row=1, column=3, pady=6, padx=3, sticky="ew")
        ttk.Button(frm_list, text="Show all",
                   command=self.refresh_list).grid(row=1, column=5, pady=6, padx=3, sticky="ew")

        self.var_total = tk.StringVar(value="Total: 0 songs, 0:00:00")
        lbl_total = ttk.Label(frm_list, textvariable=self.var_total)
        lbl_total.grid(row=2, column=0, columnspan=6,
                       pady=(4, 0), sticky="w")

        self.root.columnconfigure(1, weight=1)
        frm_list.rowconfigure(0, weight=1)

    # ---------- file browsing ----------

    def browse_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.flac *.m4a"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.var_filepath.set(path)

    def browse_cover(self) -> None:
        path = filedialog.askopenfilename(
            title="Select album cover (PNG)",
            filetypes=[("PNG images", "*.png"), ("All files", "*.*")],
        )
        if path:
            self.var_coverpath.set(path)
            self.show_cover_image(path)

    # ---------- core actions ----------

    def add_song(self) -> None:
        data = self._read_form_data()
        if data is None:
            return
        self.collector.add_song(**data)
        self.refresh_list()
        self.clear_form()

    def update_selected_song(self) -> None:
        if self.current_edit_id is None:
            messagebox.showinfo("Update", "Select one song in the list to edit.")
            return
        data = self._read_form_data()
        if data is None:
            return
        ok = self.collector.update_song(self.current_edit_id, **data)
        if not ok:
            messagebox.showerror("Update", "Could not find song to update.")
            return
        self.refresh_list()

    def clear_form(self) -> None:
        self.var_title.set("")
        self.var_artist.set("")
        self.var_duration.set("")
        self.var_genre.set("")
        self.var_rating.set("")
        self.var_filepath.set("")
        self.var_coverpath.set("")
        self.current_edit_id = None

    def _read_form_data(self) -> Dict[str, Any] | None:
        title = self.var_title.get().strip()
        artist = self.var_artist.get().strip()
        duration_text = self.var_duration.get().strip()
        genre = self.var_genre.get().strip()
        rating_text = self.var_rating.get().strip()
        filepath = self.var_filepath.get().strip()
        coverpath = self.var_coverpath.get().strip()

        if not title or not artist:
            messagebox.showwarning("Input error", "Title and Artist are required.")
            return None
        try:
            duration = int(duration_text)
            rating = int(rating_text)
        except ValueError:
            messagebox.showwarning("Input error", "Duration and rating must be integers.")
            return None
        if duration < 0:
            messagebox.showwarning("Input error", "Duration must be non-negative.")
            return None
        if not (1 <= rating <= 5):
            messagebox.showwarning("Input error", "Rating must be between 1 and 5.")
            return None

        return {
            "title": title,
            "artist": artist,
            "duration_seconds": duration,
            "genre": genre,
            "rating": rating,
            "filepath": filepath,
            "cover_path": coverpath,
        }

    def refresh_list(self, songs: List[Song] | None = None) -> None:
        if songs is None:
            songs = self.collector.list_songs()
        self.lst_songs.delete(0, tk.END)
        for s in songs:
            has_file = "🎵" if s.filepath else "—"
            text = (
                f"[{s.id}] {s.title} – {s.artist} "
                f"({s.genre}, {s.duration_seconds}s, rating {s.rating}, file {has_file})"
            )
            self.lst_songs.insert(tk.END, text)
        self.update_total_duration_label(songs)

    def _get_selected_ids(self) -> List[int]:
        selection = list(self.lst_songs.curselection())
        ids: List[int] = []
        for index in selection:
            text = self.lst_songs.get(index)
            try:
                id_part = text.split("]")[0]
                song_id = int(id_part.strip("["))
                ids.append(song_id)
            except Exception:
                pass
        return ids

    def delete_selected(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("Delete", "Please select at least one song.")
            return
        for song_id in ids:
            self.collector.remove_song_by_id(song_id)
        self.refresh_list()
        self.clear_form()

    # ---------- selection / editing ----------

    def on_song_selected(self, event: tk.Event | None = None) -> None:
        ids = self._get_selected_ids()
        if len(ids) != 1:
            self.current_edit_id = None
            self.lbl_cover.configure(text="Album cover preview\n(PNG)", image="")
            self.cover_image = None
            return
        song = self.collector.get_song_by_id(ids[0])
        if not song:
            self.current_edit_id = None
            return
        self.current_edit_id = song.id
        self._load_song_into_form(song)
        if song.cover_path and os.path.exists(song.cover_path):
            self.show_cover_image(song.cover_path)
        else:
            self.lbl_cover.configure(text="Album cover preview\n(PNG)", image="")
            self.cover_image = None

    def _load_song_into_form(self, song: Song) -> None:
        self.var_title.set(song.title)
        self.var_artist.set(song.artist)
        self.var_duration.set(str(song.duration_seconds))
        self.var_genre.set(song.genre)
        self.var_rating.set(str(song.rating))
        self.var_filepath.set(song.filepath)
        self.var_coverpath.set(song.cover_path)

    # ---------- playback ----------

    def play_selected(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            messagebox.showinfo("Play", "Please select at least one song.")
            return
        self._play_song_ids(ids)

    def play_all(self) -> None:
        songs = self.collector.list_songs()
        ids = [s.id for s in songs]
        if not ids:
            messagebox.showinfo("Play", "No songs in library.")
            return
        self._play_song_ids(ids)

    def play_random(self) -> None:
        songs = self.collector.list_songs()
        if not songs:
            messagebox.showinfo("Random", "No songs in library.")
            return
        song = random.choice(songs)
        if not song.filepath:
            messagebox.showinfo("Random", "Random song has no audio file.")
            return
        index = None
        for i in range(self.lst_songs.size()):
            if self.lst_songs.get(i).startswith(f"[{song.id}]"):
                index = i
                break
        if index is not None:
            self.lst_songs.selection_clear(0, tk.END)
            self.lst_songs.selection_set(index)
            self.lst_songs.see(index)
        self._open_audio(song.filepath)

    def _play_song_ids(self, ids: List[int]) -> None:
        paths: List[str] = []
        for song_id in ids:
            song = self.collector.get_song_by_id(song_id)
            if not song or not song.filepath:
                continue
            if os.path.exists(song.filepath):
                paths.append(song.filepath)

        if not paths:
            messagebox.showinfo("Play", "No valid audio files to play.")
            return

        if len(paths) == 1:
            self._open_audio(paths[0])
            return

        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".m3u", mode="w", encoding="utf-8"
            ) as f:
                for p in paths:
                    f.write(p + "\n")
                playlist_path = f.name
            self._open_audio(playlist_path)
        except Exception as e:
            messagebox.showerror("Play", f"Could not create playlist:\n{e}")

    def _open_audio(self, path: str) -> None:
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except Exception as e:
            messagebox.showerror("Play", f"Cannot open file:\n{e}")

    # ---------- search / sort / stats ----------

    def smart_search(self) -> None:
        keyword = self.var_search.get().strip()
        if not keyword:
            messagebox.showinfo("Search", "Enter keyword first.")
            return
        results = self.collector.search_smart(keyword)
        if not results:
            messagebox.showinfo("Search", "No matching songs.")
        self.refresh_list(results)

    def apply_sort(self) -> None:
        key = self.var_sort.get()
        self.collector.sort_songs(key)
        self.refresh_list()

    def show_stats(self) -> None:
        stats = self.collector.genre_counts()
        if not stats:
            messagebox.showinfo("Statistics", "No songs in collection.")
            return
        lines = [f"{genre}: {count} song(s)" for genre, count in stats.items()]
        messagebox.showinfo("Genre statistics", "\n".join(lines))

    # ---------- save / load ----------

    def save_library(self) -> None:
        filename = filedialog.asksaveasfilename(
            title="Save library",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            self.collector.save_to_file(filename)
            messagebox.showinfo("Save", "Library saved successfully.")
        except Exception as e:
            messagebox.showerror("Save", f"Could not save library:\n{e}")

    def load_library(self) -> None:
        filename = filedialog.askopenfilename(
            title="Load library",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not filename:
            return
        try:
            self.collector.load_from_file(filename)
            self.refresh_list()
            messagebox.showinfo("Load", "Library loaded successfully.")
        except Exception as e:
            messagebox.showerror("Load", f"Could not load library:\n{e}")

    # ---------- cover & totals ----------

    def show_cover_image(self, path: str) -> None:
        try:
            img = tk.PhotoImage(file=path)
        except Exception:
            self.lbl_cover.configure(text="Cannot load image", image="")
            self.cover_image = None
            return
        self.cover_image = img
        self.lbl_cover.configure(image=self.cover_image, text="")

    def update_total_duration_label(self, songs: List[Song]) -> None:
        total_sec = self.collector.total_duration(songs)
        minutes, seconds = divmod(total_sec, 60)
        hours, minutes = divmod(minutes, 60)
        self.var_total.set(
            f"Total: {len(songs)} song(s), {hours:d}:{minutes:02d}:{seconds:02d}"
        )


def main() -> None:
    root = tk.Tk()
    app = SongCollectorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
