<div align="center">
  <a href="https://github.com/C-Yassin/AmethystMiner" target="_blank">
    <img src="https://raw.githubusercontent.com/C-Yassin/Amethyst-Miner/6b3ae3b40d78588116eef257f2011055c34e676d/gui/logo.svg" alt="Amethyst Miner Logo">
  </a>
</div>
<p align="center">
  <a href="https://flathub.org/en/apps/io.github.C_Yassin.AmethystMiner"><img alt="Flathub" src="https://img.shields.io/badge/Flathub-Available-purple?logo=flatpak"></a>
  <a href="https://aur.archlinux.org/packages/amethystminer">
    <img alt="AUR Package" src="https://img.shields.io/aur/version/amethyst-miner?color=purple&label=AUR&logo=arch-linux">
  </a>
  <a href="https://github.com/C-Yassin/AmethystMiner/releases/latest"><img alt="GitHub Release" src="https://img.shields.io/github/v/release/C-Yassin/AmethystMiner?color=blueviolet&label=Latest%20Release"></a>
</p>

## Description

**Amethyst Miner** is a sleek, smart, and fully automated Monero (XMR) background miner built for the Linux desktop. By wrapping the immense CPU mining power of **XMRig** into a beautiful, lightweight **PyQt6** interface, Amethyst Miner makes cryptocurrency mining accessible, quiet, and effortlessly organized. 

Just enter your wallet address, and let it quietly turn your idle computer time into Monero.

## Features

- ⚡️ **Optimized Engine:** High-performance RandomX CPU mining powered directly by the latest XMRig engine.
- 🎨 **Modern Interface:** A gorgeous, native-feeling GUI built with PyQt6 featuring real-time hashrate graphs and hardware monitoring.
- 📦 **Background Mode:** Minimizes securely to the system tray, running silently in the background without interrupting your workflow.
- ❤️ **Free and Open Source:** Transparent, lightweight, and community-driven.

## Powered by XMRig

Amethyst Miner acts as a graphical and automation wrapper around **XMRig**, the industry-standard CPU miner for Monero. 

## Install
### Flatpak
```bash
flatpak install flathub io.github.C_Yassin.AmethystMiner
```
### Arch Linux (AUR)
```bash
# soon
```
### Source Code
```bash
git clone https://github.com/C-Yassin/AmethystMiner.git
cd AmethystMiner
python3 main.py
```
Because We compile XMRig inside it we need the required tools:

### For Debian or Ubuntu (APT)
```bash
sudo apt update
sudo apt install cmake libhwloc-dev libssl-dev
```

### For Arch Linux (Pacman)
```bash
sudo pacman -Syu
sudo pacman -S cmake hwloc openssl
```
If you want to dive deeper into how the mining algorithms work, understand specific CPU optimizations (like MSR mods and Huge Pages), or tweak advanced networking parameters, check out the official documentation:
- 📖 [XMRig Official Documentation](https://xmrig.com/docs)
- 🛠️ [RandomX Algorithm Details](https://xmrig.com/docs/algorithms)

## Bug Report & Feedback
If you encounter any bugs, crashes, or unintended behavior, please report them via the GitHub Issues section. Provide as much context as possible (OS, desktop environment, and terminal logs) so they can be fixed quickly.

## Contribution
Contributions are always welcome! Whether it's adding new features, optimizing the Python code, or designing new SVG icons, feel free to submit a pull request.

If you like my work, please consider giving the repository a ⭐ — thanks! ❤️
