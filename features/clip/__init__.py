"""
Clip Maker: ubah video panjang menjadi clip pendek vertikal siap upload
(TikTok, Instagram Reels, YouTube Shorts).

  api.py     rute /api/clip/*, antrian, dan pekerja
  engine.py  mesin: unduh, transkrip, deteksi momen, render, tiru gaya
"""
from .api import ID, SETTINGS, bp, start, summary

NAME = "Clip Maker"

__all__ = ["ID", "NAME", "SETTINGS", "bp", "start", "summary"]
