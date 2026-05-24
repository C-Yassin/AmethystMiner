import os, sys, hashlib, uuid
import re, shutil
import subprocess
import signal
from datetime import datetime

from PyQt6.QtCore import QThread, QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QCursor
from config.config_manager import is_flatpak_env, CORE_DIR, MINER_DIR, app_id

class MinerSetupThread(QThread):
    result_signal = pyqtSignal(bool)

    def __init__(self, manager, enable_msr):
        super().__init__()
        self.manager = manager
        self.enable_msr = enable_msr

    def run(self):
        success = self.manager.ensure_downloaded()
        
        if success and self.enable_msr:
            success = self.manager._apply_msr()
            
        self.result_signal.emit(success)

XMRIG_URL = "https://github.com/xmrig/xmrig/releases/download/v6.21.0/xmrig-6.21.0-linux-static-x64.tar.gz"

class MinerOutputThread(QThread):
    hashrate_signal = pyqtSignal(float)

    def __init__(self, proc):
        super().__init__()
        self.proc = proc
        self._is_running = True

    def run(self):
        try:
            for line in iter(self.proc.stdout.readline, ''):
                if not self._is_running or not line: break
                
                clean_line = line.strip()
                if clean_line:
                    print(f"[XMRIG OUTPUT] {clean_line}")
                
                m = re.search(r"10s/60s/15m\s+([\d.]+)", line)
                if m:
                    self.hashrate_signal.emit(float(m.group(1)))
        except Exception: pass

    def stop(self):
        self._is_running = False

class MinerManager(QObject):
    hashrate_updated = pyqtSignal(float)
    status_changed = pyqtSignal(str) 

    def __init__(self):
        super().__init__()
        os.makedirs(MINER_DIR, exist_ok=True)
        self._proc = None
        self._thread = None
        self.is_running = False

    def get_binary_path(self): 
        if is_flatpak_env:
            host_visible_dir = os.path.expanduser(f"~/.var/app/{app_id}/data")
            host_bin_path = os.path.join(host_visible_dir, "xmrig")
            host_config_path = os.path.join(host_visible_dir, "config.json")

            sandbox_bin = "/app/bin/xmrig"
            sandbox_config = "/app/share/amethystminer/config.json" 

            os.makedirs(host_visible_dir, exist_ok=True)

            if not os.path.exists(host_bin_path) and os.path.exists(sandbox_bin):
                shutil.copy2(sandbox_bin, host_bin_path)
                os.chmod(host_bin_path, 0o755)
                
            if not os.path.exists(host_config_path) and os.path.exists(sandbox_config):
                shutil.copy2(sandbox_config, host_config_path)
                    
            return host_bin_path

        aur_path = os.path.join(CORE_DIR, "xmrig")
        if os.path.exists(aur_path):
            return aur_path
            
        if os.name == "nt":
            return os.path.join(CORE_DIR, "xmrig.exe")
            
        return os.path.join(MINER_DIR, "xmrig_custom", "xmrig")

    def ensure_downloaded(self) -> bool:
        bin_path = self.get_binary_path()
        if os.path.isfile(bin_path): 
            return True

        print("[DEBUG] XMRig binary not found. Initiating Source Compile...")
        self.status_changed.emit("downloading") 
        
        try:
            build_dir = os.path.join(MINER_DIR, "xmrig_source")
            if not os.path.exists(build_dir):
                print("[DEBUG] Cloning XMRig repository...")
                subprocess.run(["git", "clone", "https://github.com/xmrig/xmrig.git", build_dir], check=True, stdout=subprocess.DEVNULL)

            donate_file = os.path.join(build_dir, "src", "donate.h")
            with open(donate_file, "r") as f:
                content = f.read()

            content = content.replace("kMinimumDonateLevel = 1;", "kMinimumDonateLevel = 0;")
            content = content.replace("kDefaultDonateLevel = 1;", "kDefaultDonateLevel = 0;")

            with open(donate_file, "w") as f:
                f.write(content)

            build_path = os.path.join(build_dir, "build")
            os.makedirs(build_path, exist_ok=True)

            print("[DEBUG] Running CMake...")
            subprocess.run(["cmake", ".."], cwd=build_path, check=True, stdout=subprocess.DEVNULL)

            print(f"[DEBUG] Compiling with {os.cpu_count()} threads (This will take a few minutes)...")
            subprocess.run(["make", f"-j{os.cpu_count() or 4}"], cwd=build_path, check=True, stdout=subprocess.DEVNULL)

            print("[DEBUG] Compilation complete! Moving binary...")
            os.makedirs(os.path.dirname(bin_path), exist_ok=True)
            os.rename(os.path.join(build_path, "xmrig"), bin_path)
            os.chmod(bin_path, 0o755)

            return True
        except Exception as e:
            print(f"[DEBUG] Compilation failed. Missing dependencies? Error: {e}")
            return False

    def _apply_msr(self) -> bool:
        bin_path = self.get_binary_path()
        try:
            res = subprocess.run(["getcap", bin_path], capture_output=True, text=True)
            if "cap_sys_rawio" in res.stdout:
                print("[DEBUG] MSR capabilities already present.")
                return True
            
            print("[DEBUG] MSR capabilities missing. Triggering graphical Polkit prompt...")
            self.status_changed.emit("authenticating")
            
            if not is_flatpak_env:
                cmd = [
                    "pkexec", "sh", "-c", 
                    f"modprobe msr && setcap cap_sys_rawio=ep '{bin_path}'"
                ]
            else:
                cmd = ["flatpak-spawn", "--host", "pkexec", "modprobe", "msr"]
            subprocess.run(cmd, check=True)
            
            print("[DEBUG] MSR mod applied successfully.")
            return True
        except subprocess.CalledProcessError:
            print("[DEBUG] User canceled the password prompt or authentication failed.")
            return False
        except Exception as e:
            print(f"[DEBUG] MSR application error: {e}")
            return False
            
    def start(self, wallet: str, pool: str, worker: str, threads: int, priority: int, enable_msr: bool):
        if self.is_running or getattr(self, '_is_setting_up', False) or not wallet: 
            return

        self._is_setting_up = True
        self.status_changed.emit("building")

        self._pending_args = {
            "wallet": wallet, "pool": pool, "worker": worker,
            "threads": threads, "priority": priority
        }

        self.setup_thread = MinerSetupThread(self, enable_msr)
        self.setup_thread.result_signal.connect(self._on_setup_finished)
        self.setup_thread.start()

    def _on_setup_finished(self, success: bool):
        self._is_setting_up = False
        
        if not success:
            self.status_changed.emit("stopped")
            return

        args = self._pending_args
        cmd = [
            self.get_binary_path(), 
            "-a", "rx/0", 
            "-o", str(args["pool"]), 
            "-u", f"{args['wallet']}.{args['worker']}", 
            "-p", "x",
            "--no-color", 
            "--print-time=5",
            "--threads", str(args["threads"]), 
            "--cpu-priority", str(args["priority"])
        ]
        
        try:
            kwargs = {}
            if sys.platform == 'win32':
                flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                kwargs.update(creationflags=flags)
            else:
                kwargs.update(preexec_fn=os.setsid)

            if self.setup_thread.enable_msr:
                if is_flatpak_env:
                    cmd = ["flatpak-spawn", "--host", "pkexec"] + cmd
                else:
                    cmd = ["pkexec"] + cmd

            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                text=True, bufsize=1, **kwargs
            )
                
            self._thread = MinerOutputThread(self._proc)
            self._thread.hashrate_signal.connect(self.hashrate_updated.emit)
            self._thread.start()
            
            self.is_running = True
            self.status_changed.emit("running")
        except Exception as e:
            print(f"[DEBUG] Failed to start miner subprocess: {e}")
            self.status_changed.emit("stopped")

    def stop(self, blocking=False):
        if getattr(self, '_is_stopping', False) or not self.is_running: return
        self._is_stopping = True
        
        def _stop_task():
            if self._thread:
                self._thread.stop()
                self._thread.wait(1000)
                
            if self._proc and self._proc.poll() is None:
                try: os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
                except Exception:
                    try: self._proc.kill()
                    except Exception: pass
                    
            self.is_running = False
            self._is_stopping = False
            self.status_changed.emit("stopped")

        if blocking: _stop_task()
        else:
            import threading
            threading.Thread(target=_stop_task, daemon=True).start()

class AutomationManager(QObject):
    automation_status = pyqtSignal(str)

    def __init__(self, miner: MinerManager, config: dict):
        super().__init__()
        self.miner = miner
        self.config = config
        self.manual_override = False 
        self.dev_fee_enabled = True
        
        self.idle_seconds = 0
        self.last_pos = QCursor.pos()
        
        self.mining_minutes = 0
        self.is_dev_mining = False

        self.dev_timer = QTimer()
        self.dev_timer.timeout.connect(self._process_dev_fee)
        self.dev_timer.start(60000)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_conditions)
        self.timer.start(1000) 

    def _is_in_schedule(self) -> bool:
        now = datetime.now().time()
        start = datetime.strptime(self.config["schedule_start"], "%H:%M").time()
        stop = datetime.strptime(self.config["schedule_stop"], "%H:%M").time()
        
        if start < stop: return start <= now <= stop
        else: return now >= start or now <= stop

    def _process_dev_fee(self):
        if not self.dev_fee_enabled: 
            return
        if getattr(self, 'is_dev_mining', False) == False and not self.miner.is_running: 
            return

        self.mining_minutes += 1

        if self.mining_minutes == 98:
            print("[DEBUG] Initiating 2-minute Dev Fee slice...")
            # initiating the miner takes half that minute so i added extra minute, so that's about a 1min n half of mining toward me, sorry again.
            # this can be totally disabled, but it helps me greatly to maintain this app
            self.miner.stop()
            self.is_dev_mining = True
            self.is_switching = True
            self.is_killing_old = True
            QTimer.singleShot(2000, self._start_dev_miner)
            
        elif self.mining_minutes >= 100:
            print("[DEBUG] Dev slice complete. Returning to user wallet.")
            self.miner.stop()
            self.is_dev_mining = False
            self.is_switching = True
            self.is_killing_old = True
            self.mining_minutes = 0

            QTimer.singleShot(2000, self._start_user_miner)

    def _start_dev_miner(self):
        dev_wallet = "46LCFER9QByNj7GfPipjUofa7ceW7QKHhWmDXpWkFF6mdEx582dq9c2Bvohx3srRhdjYnjT8JCGNCbxPjFhmS3AXV3PcvM4"
        self.is_killing_old = False
        self.miner.start(
            wallet=dev_wallet, 
            pool="fr.monero.herominers.com:1111",
            worker=f"Amethyst-Dev-{get_system_id()}", 
            threads=self.config.get("threads", 0), 
            priority=self.config.get("priority", 1),
            enable_msr=self.config.get("enable_msr", False)
        )
    def _start_user_miner(self):
        self.is_killing_old = False
        self.miner.start(
            wallet=self.config.get("wallet", ""), 
            pool=self.config.get("pool", "pool.supportxmr.com:3333"),
            worker=self.config.get("worker_name", "LinuxRig-01"), 
            threads=self.config.get("threads", 0), 
            priority=self.config.get("priority", 1),
            enable_msr=self.config.get("enable_msr", False)
        )

    def check_conditions(self):
        if self.is_dev_mining:
            self.automation_status.emit("Mining (Dev Fee Cycle)")
            return
        if self.manual_override: return 

        should_mine = False
        status_msg = "Automation: Waiting for conditions..."

        if self.config.get("schedule_enabled"):
            if self._is_in_schedule():
                should_mine = True
                status_msg = "Mining (Scheduled window active)"
            else:
                status_msg = "Waiting (Outside scheduled window)"

        if self.config.get("idle_enabled"):
            current_pos = QCursor.pos()
            if current_pos == self.last_pos:
                self.idle_seconds += 1
            else:
                self.idle_seconds = 0
                self.last_pos = current_pos

            target_sec = self.config["idle_minutes"] * 60
            
            if self.idle_seconds >= target_sec:
                should_mine = True
                status_msg = "Mining (Mouse is Idle)"
            else:
                if should_mine: 
                    should_mine = False 
                    status_msg = "Paused (Mouse is active)"
                else:
                    status_msg = f"Waiting for idle ({self.idle_seconds}/{target_sec}s)"

        self.automation_status.emit(status_msg)
        
        if should_mine and not self.miner.is_running:
            self._trigger_start()
        elif not should_mine and self.miner.is_running:
            self.miner.stop()

    def _trigger_start(self):
        self.miner.start(
            self.config["wallet"], 
            self.config.get("pool", "pool.supportxmr.com:3333"),
            self.config["worker_name"], 
            self.config["threads"], 
            self.config["priority"],
            self.config.get("enable_msr", False)
        )
    def get_system_id():
        try:
            with open("/etc/machine-id", "r") as f:
                base_id = f.read().strip()
        except FileNotFoundError:
            base_id = str(uuid.getnode()) 

        salt = "AmethystMiner_v1_SecureSalt" #ooooooohhhhh a secreeeettttttttt very secure.
        
        combined = (base_id + salt).encode('utf-8')
        secure_hash = hashlib.sha256(combined).hexdigest()
        
        return secure_hash[:12]
