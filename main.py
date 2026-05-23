#!/usr/bin/env python3
import sys
import os
import signal

from PyQt6.QtCore import Qt, QTimer, QTime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                              QHBoxLayout, QPushButton, QLabel, QFrame,
                              QStackedWidget, QLineEdit, QScrollArea, 
                              QMessageBox, QSpinBox, QFormLayout,
                              QTimeEdit, QGroupBox, QSizePolicy, QSystemTrayIcon, QMenu)
from PyQt6.QtGui import QCursor, QPainter, QColor, QAction, QPixmap, QIcon
from PyQt6.QtSvg import QSvgRenderer
from config.config_manager import GUI_DIR, load_config, save_config, get_icon_path, is_flatpak_env
from gui.gui_manager import TickCheckBox, PremiumLineChart
from core.hardware import MinerManager, AutomationManager
from core.api_manager import PoolApiThread 

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Amethyst Miner")
        self.resize(950, 650)

        self.config = load_config()
        self.miner = MinerManager()
        self.auto_mgr = AutomationManager(self.miner, self.config)

        self.miner.hashrate_updated.connect(self._update_hashrate)
        self.miner.status_changed.connect(self._update_ui_state)
        self.auto_mgr.automation_status.connect(self._update_auto_status)

        self.api_thread = None
        self.api_timer = QTimer()
        self.api_timer.timeout.connect(self._fetch_pool_stats)
        self.api_timer.start(60000)
        
        QTimer.singleShot(1000, self._fetch_pool_stats)

        self._init_ui()
        self._init_tray()
        self._apply_styles()

    def _apply_styles(self):
        try:
            with open(get_icon_path("styles.qss"), "r") as file:
                stylesheet = file.read()
            
            gui_dir_css = GUI_DIR.replace("\\", "/")
            stylesheet = stylesheet.replace("{{GUI_DIR}}", gui_dir_css)
            self.setStyleSheet(stylesheet)
        except Exception:
            pass

    def _init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self._create_tray_icon("#fff"))
        
        self.tray_menu = QMenu()

        self.action_toggle_mine = QAction("Start Miner", self)
        self.action_toggle_mine.triggered.connect(self._toggle_mining)
        self.tray_menu.addAction(self.action_toggle_mine)

        self.action_idle = QAction("Enable Idle Mining", self)
        self.action_idle.setCheckable(True)
        self.action_idle.setChecked(self.config.get("idle_enabled", False))
        self.action_idle.triggered.connect(self._tray_toggle_idle)
        self.tray_menu.addAction(self.action_idle)

        self.tray_menu.addSeparator()

        self.action_quit = QAction("Quit Miner", self)
        self.action_quit.triggered.connect(self._quit_app)
        self.tray_menu.addAction(self.action_quit)

        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self._tray_activated)

    def _create_tray_icon(self, hex_color):
        original_pixmap = QIcon(get_icon_path("tray-icon.svg")).pixmap(32, 32)
        
        colored_pixmap = QPixmap(original_pixmap.size())
        colored_pixmap.fill(Qt.GlobalColor.transparent)
        
        p = QPainter(colored_pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        p.drawPixmap(0, 0, original_pixmap)
        
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        
        p.fillRect(colored_pixmap.rect(), QColor(hex_color))
        p.end()
        
        return QIcon(colored_pixmap)

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()

    def _tray_toggle_idle(self, checked):
        self.chk_idle.setChecked(checked)
        self._save_settings()

    def _quit_app(self):
        self.miner.stop(blocking=True)
        QApplication.quit()

    def _init_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(20, 40, 20, 40)
        sb_layout.setSpacing(15)

        logo_layout = QHBoxLayout()
        logo_layout.setContentsMargins(0, 0, 0, 0)
        
        logo_icon = QLabel()
        pixmap = QPixmap(get_icon_path("logo.svg")).scaled(
            192, 192, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        logo_icon.setPixmap(pixmap)
        
        logo_layout.addWidget(logo_icon)
        logo_layout.addStretch()
        
        sb_layout.addLayout(logo_layout)

        self.nav_btns = {}
        for name, idx in [("Dashboard", 0), ("Stats", 1),("Settings", 2), ("About", 3)]:
            btn = QPushButton(name)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setObjectName("nav_btn")
            if idx == 0: btn.setChecked(True)
            btn.clicked.connect(lambda checked, i=idx: self._switch_page(i))
            self.nav_btns[idx] = btn
            sb_layout.addWidget(btn)

        sb_layout.addStretch()
        layout.addWidget(sidebar)

        self.pages = QStackedWidget()
        layout.addWidget(self.pages)

        self.pages.addWidget(self._build_dashboard())
        self.pages.addWidget(self._build_stats())  
        self.pages.addWidget(self._build_settings())
        self.pages.addWidget(self._build_about_and_support())

        self.pages.setCurrentIndex(0)

    def _switch_page(self, index):
        self.pages.setCurrentIndex(index)
        for idx, btn in self.nav_btns.items():
            btn.setChecked(idx == index)
    
    def _build_stats(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 50, 50, 50)
        
        title = QLabel("Performance & Network Stats")
        title.setObjectName("page_title")
        layout.addWidget(title)
        
        self.chart_hashrate = PremiumLineChart("Hashrate History", "#50fa7b", is_hashrate=True)
        layout.addWidget(self.chart_hashrate)
        
        layout.addSpacing(20)
        
        self.chart_balance = PremiumLineChart("Unpaid Pool Balance Growth", "#bd93f9", is_hashrate=False)
        layout.addWidget(self.chart_balance)

        return page

    def _build_about_and_support(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        title = QLabel("About & Support")
        title.setObjectName("page_title")
        layout.addWidget(title)
        
        layout.addSpacing(20)

        card = QFrame()
        card.setObjectName("dash_card")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cl = QVBoxLayout(card)
        cl.setSpacing(15)
        cl.setContentsMargins(30, 30, 30, 30)
        
        lbl_app = QLabel("Amethyst Miner v1.0.0")
        lbl_app.setStyleSheet("font-size: 22px; font-weight: bold; color: #bd93f9;")
        cl.addWidget(lbl_app)
        
        lbl_info = QLabel(
            'A lightweight, automated background miner.<br>'
        )
        lbl_info.setStyleSheet("font-size: 14px; color: #f8f8f2;")
        cl.addWidget(lbl_info)
        
        lbl_fee = QLabel(
            '<span style="color: #ffb86c;"><b>Transparency Note:</b></span> This app includes a 1% dev fee to support future updates and bug fixes.'
        )
        lbl_fee.setWordWrap(True)
        lbl_fee.setStyleSheet("font-size: 14px; color: #f8f8f2;")
        cl.addWidget(lbl_fee)
        
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background-color: #44475a; margin-top: 5px; margin-bottom: 10px;")
        cl.addWidget(div)
        
        lbl_ticket = QLabel(
            'Need help or found a bug?<br>'
            '<b>➔ <a href="https://github.com/C-Yassin/Amethyst-Miner/issues" style="color: #50fa7b; text-decoration: none;">Open a Support Ticket on GitHub</a></b>'
        )
        lbl_ticket.setOpenExternalLinks(True)
        lbl_ticket.setStyleSheet("font-size: 15px;")
        cl.addWidget(lbl_ticket)
        lbl_maintainer_info = QLabel(
            '➔ Built and maintained by <a href="https://github.com/C-Yassin" style="color: #8be9fd; text-decoration: none;">C-Yassin</a>.'
        )
        lbl_maintainer_info.setOpenExternalLinks(True)
        lbl_maintainer_info.setStyleSheet("font-size: 14px; color: #f8f8f2;")
        lbl_maintainer_info.setOpenExternalLinks(True)
        cl.addWidget(lbl_maintainer_info)
        
        layout.addWidget(card)
        layout.addStretch()

        return page

    def _build_dashboard(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Mining Dashboard")
        title.setObjectName("page_title")
        layout.addWidget(title)

        card = QFrame()
        card.setObjectName("dash_card")
        cl = QVBoxLayout(card)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setSpacing(10)

        self.lbl_status = QLabel("READY TO MINE")
        self.lbl_status.setObjectName("status_ready")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.lbl_status)

        self.lbl_hashrate = QLabel("0.00 H/s")
        self.lbl_hashrate.setObjectName("hashrate_text")
        self.lbl_hashrate.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.lbl_hashrate)

        self.lbl_unit = QLabel("Est. Profit: $0.00 / day")
        self.lbl_unit.setObjectName("profit_text")
        self.lbl_unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.lbl_unit)
        
        cl.addSpacing(20)

        self.lbl_unpaid = QLabel("Unpaid Balance: 0.000000 XMR")
        self.lbl_unpaid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_unpaid.setStyleSheet("color: #f1fa8c; font-size: 14px; font-weight: bold;")
        cl.addWidget(self.lbl_unpaid)

        self.lbl_paid = QLabel("Total Paid Out: 0.000000 XMR")
        self.lbl_paid.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_paid.setStyleSheet("color: #bd93f9; font-size: 12px;")
        cl.addWidget(self.lbl_paid)

        self.btn_power = QPushButton("START MINER (MANUAL)")
        self.btn_power.setObjectName("btn_start")
        self.btn_power.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        self.btn_power.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.btn_power.setMinimumHeight(80) 
        self.btn_power.clicked.connect(self._toggle_mining)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.btn_power)
        cl.addLayout(btn_layout)

        self.lbl_auto_info = QLabel("Automation: Off")
        self.lbl_auto_info.setObjectName("auto_info_text")
        self.lbl_auto_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.lbl_auto_info)

        layout.addWidget(card)
        layout.addStretch()
        return page

    def _build_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 50, 50, 50)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Configuration")
        title.setObjectName("page_title")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settings_scroll")
        inner = QWidget()
        form = QVBoxLayout(inner)
        form.setSpacing(20)

        grp_miner = QGroupBox("Miner Configuration")
        ml = QFormLayout(grp_miner)
        
        ml.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ml.setHorizontalSpacing(30)
        ml.setVerticalSpacing(15)

        self.inp_wallet = QLineEdit(self.config["wallet"])
        self.inp_wallet.setPlaceholderText("XMR Wallet Address")
        self.inp_wallet.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.inp_wallet.setToolTip("Enter your primary Monero (XMR) receiving address here.")
        ml.addRow("Monero Wallet:", self.inp_wallet)

        self.inp_pool = QLineEdit(self.config.get("pool", "")) 
        self.inp_pool.setPlaceholderText("pool.supportxmr.com:3333")
        self.inp_pool.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.inp_pool.setToolTip("The mining pool address and port (e.g., pool.supportxmr.com:3333).")
        ml.addRow("Mining Pool:", self.inp_pool)

        self.inp_worker = QLineEdit(self.config["worker_name"])
        self.inp_worker.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.inp_worker.setToolTip("A name to identify this specific computer on your pool dashboard.")
        ml.addRow("Worker Name:", self.inp_worker)

        self.spin_threads = QSpinBox()
        self.spin_threads.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_threads.setRange(1, os.cpu_count() or 16)
        self.spin_threads.setValue(self.config["threads"])
        self.spin_threads.setToolTip("Number of CPU threads to use. Leave 1-2 threads free for normal PC usage.")
        ml.addRow("CPU Threads:", self.spin_threads)

        self.spin_priority = QSpinBox()
        self.spin_priority.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_priority.setRange(0, 5)
        self.spin_priority.setValue(self.config["priority"])
        self.spin_priority.setToolTip("Set process priority (0 idle, 2 normal to 5 highest)")
        ml.addRow("CPU Priority:", self.spin_priority)

        self.chk_msr = TickCheckBox("Enable MSR Hardware Mod (Requires Root Password once)")
        self.chk_msr.setChecked(self.config.get("enable_msr", False))
        self.chk_msr.setToolTip("Modifies CPU hardware prefetchers for a 15-20% hashrate boost." if not is_flatpak_env else "MSR modifications require root access, which is blocked by the Flatpak sandbox.")
        if is_flatpak_env: self.chk_msr.setEnabled(False)
        ml.addRow("", self.chk_msr)

        self.lbl_github = QLabel('<a href="https://github.com/C-Yassin/Amethyst-Miner/wiki/How-to-Enable-MSR-via-GRUB" style="color: #8be9fd; text-decoration: none;">[?] Help: How to fix MSR blocking via GRUB</a>')
        self.lbl_github.setOpenExternalLinks(True)
        self.lbl_github.setToolTip("Click to open the GRUB tutorial in your web browser.")
        ml.addRow("", self.lbl_github)
        
        form.addWidget(grp_miner)

        grp_auto = QGroupBox("Smart Automation")
        al = QVBoxLayout(grp_auto)

        self.chk_autostart = TickCheckBox("Start Amethyst Miner automatically on system boot")
        self.chk_autostart.setChecked(self.config.get("autostart_enabled", False))
        self.chk_autostart.setToolTip("Runs silently in the system tray when you log in.")
        al.addWidget(self.chk_autostart)

        self.chk_idle = TickCheckBox("Enable Idle Mining (Pauses on mouse move)")
        self.chk_idle.setChecked(self.config["idle_enabled"])
        self.chk_idle.setToolTip("Automatically starts mining when you step away from the computer.")
        al.addWidget(self.chk_idle)
        
        self.idle_params_widget = QWidget()
        idle_layout = QFormLayout(self.idle_params_widget)
        idle_layout.setContentsMargins(25, 0, 0, 10)
        
        idle_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        idle_layout.setHorizontalSpacing(30)
        idle_layout.setVerticalSpacing(15)

        self.chk_idle.toggled.connect(lambda checked: self.action_idle.setChecked(checked))

        self.chk_schedule = TickCheckBox("Enable Time Schedule")
        self.chk_schedule.setChecked(self.config["schedule_enabled"])
        self.chk_schedule.setToolTip("Only allow mining between specific times (e.g., overnight).")
        al.addWidget(self.chk_schedule)

        self.spin_idle = QSpinBox()
        self.spin_idle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.spin_idle.setRange(1, 60)
        self.spin_idle.setSuffix(" minutes")
        self.spin_idle.setValue(self.config["idle_minutes"])
        idle_layout.addRow("Consider Idle After:", self.spin_idle)
        
        al.addWidget(self.idle_params_widget)

        self.schedule_params_widget = QWidget()
        schedule_layout = QFormLayout(self.schedule_params_widget)
        schedule_layout.setContentsMargins(25, 0, 0, 10)
        
        schedule_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        schedule_layout.setHorizontalSpacing(30)
        schedule_layout.setVerticalSpacing(15)

        self.time_start = QTimeEdit(QTime.fromString(self.config["schedule_start"], "HH:mm"))
        self.time_start.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.time_start.setDisplayFormat("HH:mm")
        schedule_layout.addRow("Start Mining At:", self.time_start)

        self.time_stop = QTimeEdit(QTime.fromString(self.config["schedule_stop"], "HH:mm"))
        self.time_stop.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.time_stop.setDisplayFormat("HH:mm")
        schedule_layout.addRow("Stop Mining At:", self.time_stop)

        al.addWidget(self.schedule_params_widget)

        self.chk_idle.toggled.connect(self.idle_params_widget.setVisible)
        self.idle_params_widget.setVisible(self.chk_idle.isChecked())

        self.chk_schedule.toggled.connect(self.schedule_params_widget.setVisible)
        self.schedule_params_widget.setVisible(self.chk_schedule.isChecked())

        form.addWidget(grp_auto)
        
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        btn_save = QPushButton("SAVE CONFIGURATION")
        btn_save.setObjectName("btn_start")
        btn_save.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_save.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_save.setMinimumHeight(60)
        btn_save.clicked.connect(self._save_settings)
        layout.addWidget(btn_save)

        return page

    def _toggle_mining(self):
        if not self.config["wallet"]:
            QMessageBox.critical(self, "Error", "Please configure your XMR Wallet in the Settings tab first.")
            self._switch_page(1)
            return

        if self.miner.is_running:
            self.auto_mgr.manual_override = False
            self.miner.stop()
        else:
            self.auto_mgr.manual_override = True
            self.lbl_auto_info.setText("Automation Disabled (Manual Override Active)")
            self.miner.start(
                self.config["wallet"], 
                self.config["pool"],
                self.config["worker_name"], 
                self.config["threads"], 
                self.config["priority"],
                self.config.get("enable_msr", False)
            )

    def _fetch_pool_stats(self):
        if not self.config.get("wallet"):
            return
            
        pool_address = self.config.get("pool", "")
        self.api_thread = PoolApiThread(self.config["wallet"], pool_address)
        self.api_thread.stats_updated.connect(self._update_balance_ui)
        self.api_thread.start()

    def _update_balance_ui(self, stats: dict):
        if hasattr(self, 'lbl_unpaid'):
            self.lbl_unpaid.setText(f"Unpaid Balance: {stats['unpaid']:.8f} XMR")
        if hasattr(self, 'lbl_paid'):
            self.lbl_paid.setText(f"Total Paid Out: {stats['paid']:.8f} XMR")
        
        if hasattr(self, 'chart_balance'):
            self.chart_balance.update_data(stats['unpaid'])

    def _update_hashrate(self, hr: float):
        if getattr(self.auto_mgr, 'is_killing_old', False):
            return
            
        if getattr(self.auto_mgr, 'is_switching', False):
            if hr > 0.0:
                self.auto_mgr.is_switching = False
            else:
                return

        daily_profit = hr * 0.0000288
        units = ['H/s', 'kH/s', 'MH/s']
        idx = 0
        display_hr = hr
        
        while display_hr >= 1000.0 and idx < len(units) - 1:
            display_hr /= 1000.0
            idx += 1
        
        self.lbl_hashrate.setText(f"{display_hr:.2f} {units[idx]}")
        
        if hasattr(self, 'lbl_unit'):
            self.lbl_unit.setText(f"Est. Profit: ${daily_profit:.4f} / day")
            
        if hasattr(self, 'chart_hashrate'):
            self.chart_hashrate.update_data(hr)

    def _update_ui_state(self, state: str):
        if getattr(self.auto_mgr, 'is_switching', False):
            return

        if state == "running":
            self.lbl_status.setText("MINING ACTIVE")
            self.lbl_status.setObjectName("status_running")
            self.btn_power.setText("STOP MINER")
            self.btn_power.setObjectName("btn_stop")
            self.btn_power.setEnabled(True)
            
            self.action_toggle_mine.setText("Stop Miner")
            self.tray_icon.setIcon(self._create_tray_icon("#50fa7b"))
            
        elif state in ["downloading", "building"]:
            self.lbl_status.setText("BUILDING MINER (Takes 2-5 mins)...")
            self.lbl_status.setObjectName("status_ready")
            self.btn_power.setText("COMPILING FROM SOURCE...")
            self.btn_power.setEnabled(False)
            
        elif state == "authenticating":
            self.lbl_status.setText("WAITING FOR ROOT PASSWORD...")
            self.btn_power.setText("CHECK POLKIT POPUP")
            self.btn_power.setEnabled(False)
            
        else:
            self.lbl_status.setText("MINER STOPPED")
            self.lbl_status.setObjectName("status_ready")
            self.btn_power.setText("START MINER (MANUAL)")
            self.btn_power.setObjectName("btn_start")
            self.btn_power.setEnabled(True)
            self.lbl_hashrate.setText("0.00 H/s")
            
            if hasattr(self, 'lbl_unit'):
                self.lbl_unit.setText("Est. Profit: $0.00 / day")
                
            self.action_toggle_mine.setText("Start Miner")
            self.tray_icon.setIcon(self._create_tray_icon("#fff"))
            
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)
        self.btn_power.style().unpolish(self.btn_power)
        self.btn_power.style().polish(self.btn_power)

    def _update_auto_status(self, msg: str):
        if not self.auto_mgr.manual_override:
            if not self.config["idle_enabled"] and not self.config["schedule_enabled"]:
                self.lbl_auto_info.setText("Automation: Disabled in settings")
            else:
                self.lbl_auto_info.setText(msg)

    def _toggle_autostart(self, enable: bool):
        app_name = "Amethyst Miner"

        if os.name == 'nt':
            import winreg
            try:
                reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                if getattr(sys, "frozen", False):
                    exec_cmd = f'"{sys.executable}"'
                else:
                    script_path = os.path.abspath(sys.argv[0])
                    exec_cmd = f'"{sys.executable}" "{script_path}"'

                exec_cmd += " --start-minimized"

                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE
                ) as key:
                    if enable:
                        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exec_cmd)
                        print("[DEBUG] Autostart enabled (Windows).")
                    else:
                        try:
                            winreg.DeleteValue(key, app_name)
                            print("[DEBUG] Autostart disabled (Windows).")
                        except FileNotFoundError:
                            pass
            except Exception as e:
                print(f"[DEBUG] Windows autostart failed: {e}")
            return

        autostart_dir = os.path.expanduser("~/.config/autostart")
        desktop_file = os.path.join(autostart_dir, "amethyst-miner.desktop")

        if enable:
            os.makedirs(autostart_dir, exist_ok=True)
            if getattr(sys, 'frozen', False):
                exec_cmd = f"{sys.executable}"
            else:
                script_path = os.path.abspath(sys.argv[0])
                exec_cmd = f"{sys.executable} {script_path}"
            
            exec_cmd += " --start-minimized"
            
            content = f"""[Desktop Entry]
Type=Application
Name={app_name}
Comment=Automated Background Miner
Exec={exec_cmd}
Icon=utilities-terminal
Terminal=false
Categories=Network;Utility;
StartupNotify=false
"""
            try:
                with open(desktop_file, "w") as f:
                    f.write(content)
                print(f"[DEBUG] Autostart enabled: {desktop_file}")
            except Exception as e:
                print(f"[DEBUG] Failed to enable autostart: {e}")
        else:
            if os.path.exists(desktop_file):
                try:
                    os.remove(desktop_file)
                    print("[DEBUG] Autostart disabled.")
                except Exception as e:
                    print(f"[DEBUG] Failed to disable autostart: {e}")

    def _save_settings(self):
        self.config["wallet"] = self.inp_wallet.text().strip()
        self.config["pool"] = self.inp_pool.text().strip()
        self.config["worker_name"] = self.inp_worker.text().strip() or "LinuxRig"
        self.config["threads"] = self.spin_threads.value()
        self.config["enable_msr"] = self.chk_msr.isChecked()
        
        self.config["idle_enabled"] = self.chk_idle.isChecked()
        self.config["idle_minutes"] = self.spin_idle.value()
        
        self.config["schedule_enabled"] = self.chk_schedule.isChecked()
        self.config["schedule_start"] = self.time_start.time().toString("HH:mm")
        self.config["schedule_stop"] = self.time_stop.time().toString("HH:mm")
        
        is_autostart = self.chk_autostart.isChecked()
        if self.config.get("autostart_enabled") != is_autostart:
            self._toggle_autostart(is_autostart)
        self.config["autostart_enabled"] = is_autostart

        save_config(self.config)
        self.auto_mgr.config = self.config
        
        QMessageBox.information(self, "Saved", "Settings saved. If the miner is running, restart it to apply thread changes.")

    def closeEvent(self, event):
        """Minimize to tray instead of closing."""
        event.ignore()
        self.hide()
        if self.config.get("already_seen_message"):
            self.config["already_seen_message"] = False
            save_config(self.config)
            self.tray_icon.showMessage(
                "Amethyst Miner", 
                "Miner is running in the background.", 
                QSystemTrayIcon.MessageIcon.Information, 
                2000
            )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    icon_path = get_icon_path("amethyst.svg")
    
    app_icon = QIcon(icon_path)
    
    app.setStyle("Fusion")
    app.setWindowIcon(app_icon)
    app.setQuitOnLastWindowClosed(False)
    
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    win = MainWindow()
    if "--start-minimized" not in sys.argv:
        win.show()
    sys.exit(app.exec())
