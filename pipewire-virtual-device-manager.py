import subprocess
import sys
import json
import argparse
import os
import traceback
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton,
                             QHBoxLayout, QWidget, QLabel, QTableWidget,
                             QTableWidgetItem, QHeaderView, QMessageBox,
                             QDialog, QFormLayout, QLineEdit, QVBoxLayout,
                             QDialogButtonBox, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QIcon, QPalette, QDesktopServices


relVersion = "0.5.0-Source"  # Remember to change this every release
isRelease = False  # Remember to set this to true for release versions ONLY


# Configuration file
CONFIG_FILE = "devices.json"


# I spent way too much time on this
# Logging system
def print_formatted(text, type="info"):
    # Hides debug lines depending on command-line arguments
    if type == "debug" and not (cmdargs.debug or cmdargs.DEBUG) or type == "DEBUG" and not cmdargs.DEBUG:
        return

    # Standard ANSI escape codes for terminal formatting
    class Colors:
        RED = '\033[91m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        MAGENTA = '\033[95m'
        CYAN = '\033[96m'
        WHITE = '\033[97m'
        RESET = '\033[0m'

    # Case sensitive, "debug" and "DEBUG" are different
    color_map = {
        "info": Colors.WHITE,
        "error": Colors.RED,
        "debug": Colors.BLUE,
        "DEBUG": Colors.CYAN,
        "warning": Colors.YELLOW,
        "success": Colors.GREEN
    }
    color = color_map.get(type, Colors.MAGENTA)  # Uses magenta as a fallback

    label = f"[{type.upper()}]"
    textform = f"    {label:<12} {text}"

    print(f"{color}{textform}{Colors.RESET}")


# Argument parsing
argparser = argparse.ArgumentParser()
debugmode = argparser.add_mutually_exclusive_group()

# Enables basic debug mode if -d or --debug
debugmode.add_argument('-d', '--debug', action='store_true', help='Show basic debugging information.')

# Enables advanced debug mode if -D or --DEBUG
debugmode.add_argument('-D', '--DEBUG', action='store_true', help='Show advanced debugging information.')

cmdargs = argparser.parse_args()
if cmdargs.debug:
    print_formatted("Debug mode enabled!", "debug")


# Config loading
def load_devices_config():
    if not os.path.exists(CONFIG_FILE):
        print_formatted(f"Config file {CONFIG_FILE} not found. Creating default...", "warning")
        if not create_default_config():
            return {}

    try:
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)

        devices = {}
        for item in data:
            name = item["name"]

            devices[name] = {
                "sink_name": item["sink_name"],
                "description": item["description"],
                "slaves": item["slaves"]
            }
        return devices
    except json.JSONDecodeError:
        print_formatted(f"Invalid JSON in {CONFIG_FILE}!", "error")
        return {}
    except Exception as e:
        print_formatted(f"Error loading config: {e}", "error")
        return {}


def save_devices_config(devices):
    data = []
    for name, info in devices.items():
        data.append({
            "name": name,
            "sink_name": info["sink_name"],
            "description": info["description"],
            "slaves": info["slaves"]
        })

    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print_formatted(f"Config saved to {CONFIG_FILE}", "success")
        return True
    except Exception as e:
        print_formatted(f"Failed to save config: {e}", "error")
        return False


def create_default_config():
    default_config = []

    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(default_config, f, indent=2)
        print_formatted(f"Created empty config: {CONFIG_FILE}", "success")
        return True
    except Exception as e:
        print_formatted(f"Failed to create config: {e}", "error")
        return False


# This is used to get and parse data related to PipeWire devices
# Used when loading the device creation dialog to get available devices, And to poll data related to loaded modules.
# Sorry that this is way to complex, I suck at Python.
def get_available_sinks():
    try:
        result = subprocess.run(
            ["pactl", "list", "sinks"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            print_formatted(f"pactl list sinks error: {result.stderr}", "error")
            return {}

        if not result.stdout.strip():
            print_formatted("pactl list sinks returned empty output.", "error")
            return {}

        sinks = {}
        current_sink = None

        for line in result.stdout.splitlines():  # Parses each line and saves the relevant data
            if not isinstance(line, str):
                print_formatted(f"Line is not a string: {type(line)}", "debug")
                continue

            if not line.strip():
                continue

            stripped = line.strip()

            if stripped.startswith("Sink #"):  # Starts a new device entry
                if current_sink and current_sink.get("name"):
                    sinks[current_sink["name"]] = current_sink  # Saves the previous one if it exists
                current_sink = {"name": None, "description": "Unknown", "state": "Unknown", "volume": "N/A", "mute": "N/A"}  # Creates a blank device entry
            elif current_sink is not None:  # Parses the line and adds relevant data to the current entry

                if stripped.startswith("Name:"):  # Name (internal name)
                    parts = stripped.split(":", 1)
                    if len(parts) > 1:
                        current_sink["name"] = parts[1].strip()

                elif stripped.startswith("device.description = "):  # Description (display name)
                    desc = stripped[len("device.description = "):].strip()
                    if desc.startswith('"') and desc.endswith('"'):
                        desc = desc[1:-1]
                    current_sink["description"] = desc

                elif stripped.startswith("State:"):  # State (whether it's playing, idle or suspended.)
                    parts = stripped.split(":", 1)
                    if len(parts) > 1:
                        current_sink["state"] = parts[1].strip()

                elif stripped.startswith("Volume:"):  # Volume
                    volume_str = stripped.split(":", 1)[1].strip()
                    if "%" in volume_str:
                        current_sink["volume"] = volume_str.split("%")[1].split()[-1] + "%"

                elif stripped.startswith("Mute:"):  # Mute
                    parts = stripped.split(":", 1)
                    if len(parts) > 1:
                        current_sink["mute"] = parts[1].strip()

        if current_sink and current_sink.get("name"):
            sinks[current_sink["name"]] = current_sink  # Saves the last entry

        print_formatted(f"Found {len(sinks)} available sinks with descriptions.", "debug")
        return sinks
    except Exception as e:
        print_formatted(f"Error getting sinks: {e}", "error")
        traceback.print_exc()
        return {}


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        self.setWindowIcon(QIcon.fromTheme("help-about"))
        self.setMinimumWidth(300)
        self.setMinimumHeight(200)

        print_formatted("AboutDialog opened.", "debug")

        palette = self.palette()
        link_color = palette.color(QPalette.ColorRole.Link)

        layout = QVBoxLayout()

        form = QFormLayout()
        form.setSpacing(10)

        # Version
        version_label = QLabel(relVersion if isRelease else f"{relVersion} (Non-release)")
        form.addRow("<b>Version:</b>", version_label)

        # Author
        author_label = QLabel("TheWindowAlt")
        form.addRow("<b>Author:</b>", author_label)

        # License
        css_color = f"color: {link_color.name()}; text-decoration: underline; cursor: pointer;"
        license_label = QLabel(
            f"<span style='{css_color}'>AGPL v3.0</span>"
        )
        license_label.setTextFormat(Qt.TextFormat.RichText)
        license_label.setOpenExternalLinks(True)
        license_label.setCursor(Qt.CursorShape.PointingHandCursor)
        license_label.mousePressEvent = self.on_license_click
        form.addRow("<b>License:</b>", license_label)

        # Source
        source_label = QLabel("<a href='https://github.com/TheWindowAlt/pipewire-virtual-device-manager'>GitHub</a>")
        source_label.setTextFormat(Qt.TextFormat.RichText)
        source_label.setOpenExternalLinks(True)
        form.addRow("<b>Source:</b>", source_label)

        layout.addLayout(form)

        # Button
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
        )
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def on_license_click(self, event):
        dialog = QDialog(self)
        dialog.setWindowTitle("AGPL v3.0 License")
        dialog.setMinimumSize(500, 325)
        dialog.setMaximumSize(500, 325)

        layout = QVBoxLayout(dialog)

        text = QLabel("""
PipeWire Virtual Device Manager
<p style="margin: 0;">Copyright (C) 2026 TheWindowAlt</p>
<p>This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.</p>
<p>This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.</p>
<p>You should have received a copy of the GNU Affero General Public License along with this program. If not, see <a href='https://www.gnu.org/licenses/' >https://www.gnu.org/licenses/</a>.</p>
    """)
        text.setWordWrap(True)
        text.setOpenExternalLinks(True)
        text.setTextFormat(Qt.TextFormat.RichText)

        layout.addWidget(text)

        button_layout = QHBoxLayout()

        # Read More
        web_btn = QPushButton("Read More")
        web_btn.setIcon(QIcon.fromTheme("document-open-remote"))
        web_btn.setToolTip("https://www.gnu.org/licenses/agpl-3.0.en.html")
        web_btn.clicked.connect(self.open_license_url)
        button_layout.addWidget(web_btn)

        button_layout.addStretch()

        # Close
        close_btn = QPushButton("Close")
        close_btn.setIcon(QIcon.fromTheme("dialog-cancel"))
        close_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

        dialog.exec()

    def open_license_url(self):
        QDesktopServices.openUrl(QUrl("https://www.gnu.org/licenses/agpl-3.0.en.html"))


# Device creation dialog
class AddDeviceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Virtual Device")
        self.setWindowIcon(QIcon.fromTheme("audio-card"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        print_formatted("AddDeviceDialog opened.", "debug")

        layout = QVBoxLayout()

        form = QFormLayout()

        # Device Name
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("The display name of the device.")
        form.addRow("Device Name", self.name_input)

        # Sink Name
        self.sink_input = QLineEdit()
        self.sink_input.setPlaceholderText("The internal name of the device.")
        form.addRow("Sink Name", self.sink_input)

        # Description
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("An optional description of the device.")
        form.addRow("Description", self.desc_input)

        # Available Sinks
        self.sinks_list = QListWidget()
        self.sinks_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        form.addRow("Available Sinks", self.sinks_list)

        self.load_available_sinks()  # Populates the Available Sinks list

        layout.addLayout(form)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def load_available_sinks(self):
        sinks = get_available_sinks()  # Gets all the available devices
        print_formatted(f"Found {len(sinks)} available sinks.", "debug")

        for sink_name, sink_info in sinks.items():  # Goes through each one
            display_text = f"{sink_info['description']}"  # Gets the display name (description)

            item = QListWidgetItem(display_text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

            # Sets the state and other properties
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, sink_name)  # Sets the key to the internal name
            item.setToolTip(f"{sink_name}")

            self.sinks_list.addItem(item)

    def get_data(self):  # Gets and formats the dialog input data
        selected_sinks = []
        for i in range(self.sinks_list.count()):  # Goes through each available sink
            item = self.sinks_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:  # If it's checked adds it to the list
                selected_sinks.append(item.data(Qt.ItemDataRole.UserRole))

        # Puts the data into a dictonary
        data = {
            "name": self.name_input.text().strip(),
            "sink_name": self.sink_input.text().strip(),
            "description": self.desc_input.text().strip(),
            "slaves": selected_sinks
        }
        print_formatted(f"Dialog data: {data}", "DEBUG")
        return data

    # Handles data validation before saving when accept is pressed
    def accept(self):
        data = self.get_data()

        # Checks for Device Name
        if not data["name"]:
            print_formatted("Validation failed: Device Name is empty.", "error")
            QMessageBox.warning(self, "Validation Error", "Device Name is required.")
            return

        # Checks for Sink Name
        if not data["sink_name"]:
            print_formatted("Validation failed: Sink Name is empty.", "error")
            QMessageBox.warning(self, "Validation Error", "Sink Name is required.")
            return

        # Checks for Selected Sinks
        if not data["slaves"]:
            print_formatted("Validation failed: No slave devices provided.", "error")
            QMessageBox.warning(self, "Validation Error", "At least one slave device is required.")
            return

        # Description is optional, so that isn't checked

        print_formatted(f"Validation passed for device: {data['name']}", "debug")
        super().accept()


# Main application
class PipeWireManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.is_visible = True
        self.setWindowTitle("PipeWire Virtual Device Manager")
        self.setWindowIcon(QIcon.fromTheme("audio-card"))
        self.resize(800, 400)
        self.setMinimumSize(800, 400)

        self.devices = load_devices_config()  # Loads the config
        self.last_sink_state = {}
        self._refresh_lock = False

        print_formatted(f"Loaded {len(self.devices)} devices from {CONFIG_FILE}.", "info")

        self.init_ui()

        # Automatically polls the refresh code
        # Only polls if there are modules actually loaded
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_status)
        self.refresh_timer.start(500)
        print_formatted("Polling timer started.", "debug")

        self.refresh_status()  # Refreshes the UI

    # This cleanly stops the polling timer when the app is closed
    def closeEvent(self, event):
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        super().closeEvent(event)

    # Initially triggers column scale handling
    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.force_resize_layout)

    # Handles scaling for the table columns
    # First and second column are autoscaled with a 1:2 ratio
    # Third and fourth are fixed at 100 and aren't handled by this
    def force_resize_layout(self):
        if not self.table.isVisible() or self.table.columnCount() < 4:
            return

        actions_width = self.table.columnWidth(3)
        status_width = self.table.columnWidth(2)

        viewport_width = self.table.viewport().width()

        available_width = viewport_width - actions_width - status_width

        if available_width <= 0:
            return

        part_width = available_width / 3.0

        w_name = int(part_width * 1)
        w_desc = int(part_width * 2)

        w_desc += (available_width - w_name - w_desc)

        self.table.setColumnWidth(0, w_name)
        self.table.setColumnWidth(1, w_desc)

    # Triggers the column scale handling when the window size changes
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.force_resize_layout()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()

        btn_layout = QHBoxLayout()

        # Add New Device Button
        add_btn = QPushButton()
        add_btn.setIcon(QIcon.fromTheme("list-add"))
        add_btn.setToolTip("Add New Device")
        add_btn.clicked.connect(self.add_device)

        # About Button
        about_btn = QPushButton()
        about_btn.setIcon(QIcon.fromTheme("help-about"))
        about_btn.setToolTip("About")
        about_btn.clicked.connect(lambda: AboutDialog(self).exec())

        # Add buttons to the layout
        btn_layout.addWidget(add_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(about_btn)

        layout.addLayout(btn_layout)

        # The device list
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Device Name", "Description", "Status", "Actions"])

        # Device Name and Description
        # Autoscaled by force_resize_layout()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)

        # Actions
        # Fixed scaling (100)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 100)

        # Status
        # Fixed scaling (100)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 100)

        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout.addWidget(self.table)
        central_widget.setLayout(layout)

    # Loaded module parser
    # Gets all modules and parses to find which modules are loaded
    def get_all_modules(self):
        try:
            print_formatted("Fetching module list...", "debug")
            result = subprocess.run(
                ["pactl", "list", "modules", "short"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                print_formatted(f"pactl returned error code {result.returncode}", "error")
                print_formatted(f"stderr: {result.stderr}", "debug")
                return {}

            if not result.stdout.strip():
                print_formatted("pactl output is empty!", "error")
                return {}

            print_formatted(f"pactl output: {result.stdout}", "DEBUG")
            modules = {}
            line_count = 0
            matched_count = 0

            # Parse each line
            for line in result.stdout.splitlines():
                line_count += 1
                line = line.strip()
                # Skips parsing if line is empty, doesn't start with the ID, or is a "{"
                if not line or not line[:1].isdigit() or '{' in line:
                    print_formatted(f"Skipping invalid line {line_count}: {line}", "DEBUG")
                    continue

                parts = line.split(None, 2)
                if len(parts) < 3:  # Skips parsing if line is too short
                    print_formatted(f"Skipping short line {line_count}: {line}", "DEBUG")
                    continue

                module_id = parts[0]  # ID
                module_name = parts[1]  # Internal name
                arguments = parts[2]  # Any other properties

                print_formatted(f"Line {line_count}: ID={module_id}, Name={module_name}, Args={arguments}", "DEBUG")

                # Saves loaded modules
                for name, info in self.devices.items():
                    target = info["sink_name"]
                    if f"sink_name={target} " in arguments:
                        print_formatted(f"Matched {name} (ID: {module_id})", "success")
                        modules[target] = module_id
                        matched_count += 1
                        break

            print_formatted(f"Parsed {line_count} lines, found {matched_count} matching modules: {modules}", "debug")
            return modules

        except subprocess.TimeoutExpired:
            print_formatted("pactl command timed out!", "error")
            return {}
        except Exception as e:
            print_formatted(f"Unexpected error in get_all_modules: {e}", "error")
            import traceback
            traceback.print_exc()
            return {}

    # Refresh handler
    # Runs every poll
    # Checks for changes and only repaints UI if changed
    # Stops polling if no modules are loaded
    # Way too complex, sorry
    def refresh_status(self):
        if self._refresh_lock:
            return
        self._refresh_lock = True

        try:
            if not self.devices:
                if self.table.rowCount() != 0:
                    print_formatted("No devices configured. Table is empty.", "info")
                    self.table.setRowCount(0)
                    self.last_sink_state = {}

                if self.refresh_timer.isActive():
                    print_formatted("No devices configured. Stopping polling timer.", "debug")
                    self.refresh_timer.stop()
                return

            sink_details = get_available_sinks()
            modules = self.get_all_modules()

            current_state_snapshot = {}
            for sink_name, sink_info in sink_details.items():
                module_id = modules.get(sink_name)
                status = "Loaded" if module_id else "Unloaded"
                state = sink_info.get("state", "Unknown")
                volume = sink_info.get("volume", "N/A")
                mute = sink_info.get("mute", "no")

                current_state_snapshot[sink_name] = (status, state, volume, mute)

            has_changed = False

            if set(current_state_snapshot.keys()) != set(self.last_sink_state.keys()):
                has_changed = True
            else:
                for sink_name, data in current_state_snapshot.items():
                    if self.last_sink_state.get(sink_name) != data:
                        has_changed = True
                        break

            if not has_changed:
                print_formatted("No changes detected. Skipping UI update.", "DEBUG")
                return

            self.last_sink_state = current_state_snapshot

            device_count = len(self.devices)
            loaded_count = sum(1 for info in self.devices.values() if info["sink_name"] in modules)

            print_formatted(f"Found {loaded_count} out of {device_count} devices loaded.", "info")

            if loaded_count > 0 and not self.refresh_timer.isActive():
                print_formatted("Modules loaded. Resuming polling timer.", "debug")
                self.refresh_timer.start(500)
            elif loaded_count == 0 and self.refresh_timer.isActive():
                print_formatted("No modules loaded. Stopping polling timer.", "debug")
                self.refresh_timer.stop()

            self.table.setRowCount(device_count)

            for row, (name, info) in enumerate(self.devices.items()):
                sink_name = info["sink_name"]
                module_id = modules.get(sink_name)
                sink_info = sink_details.get(sink_name, {})

                self.table.setItem(row, 0, QTableWidgetItem(name))
                self.table.setItem(row, 1, QTableWidgetItem(info["description"]))

                status_text = ""
                tooltip_text = ""
                load_button = False

                if module_id:
                    status_text = "Loaded"
                    load_button = False
                else:
                    status_text = "Unloaded"
                    load_button = True

                volume = sink_info.get("volume", "N/A")
                mute = sink_info.get("mute", "no")
                tooltip_text = f"Volume: {volume}\nMute: {'Yes' if mute == 'yes' else 'No'}"

                status_widget = QTableWidgetItem(status_text)
                status_widget.setToolTip(tooltip_text)

                state_val = sink_info.get('state', 'Unknown')
                if state_val == "RUNNING":
                    status_widget.setIcon(QIcon.fromTheme("media-playback-start"))
                elif state_val == "IDLE":
                    status_widget.setIcon(QIcon.fromTheme("media-playback-pause"))
                else:
                    status_widget.setIcon(QIcon.fromTheme("media-playback-stop"))

                status_widget.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if module_id:
                    status_widget.setForeground(Qt.GlobalColor.darkGreen)
                else:
                    status_widget.setForeground(Qt.GlobalColor.darkRed)

                self.table.setItem(row, 2, status_widget)

                btn_container = QWidget()
                btn_layout = QHBoxLayout(btn_container)
                btn_layout.setContentsMargins(2, 2, 2, 2)

                if load_button:
                    load_btn = QPushButton()
                    load_btn.setIcon(QIcon.fromTheme("media-playback-start"))
                    load_btn.setToolTip("Load")
                    load_btn.setStyleSheet("border: none;")
                    load_btn.clicked.connect(lambda checked, n=name: self.load_device(n))
                    btn_layout.addWidget(load_btn)
                else:
                    unload_btn = QPushButton()
                    unload_btn.setIcon(QIcon.fromTheme("media-playback-stop"))
                    unload_btn.setToolTip("Unload")
                    unload_btn.setStyleSheet("border: none;")
                    unload_btn.clicked.connect(lambda checked, n=name: self.unload_device(n))
                    btn_layout.addWidget(unload_btn)

                edit_btn = QPushButton()
                edit_btn.setIcon(QIcon.fromTheme("edit"))
                edit_btn.setToolTip("Edit")
                edit_btn.setStyleSheet("border: none;")
                edit_btn.clicked.connect(lambda checked, n=name: self.edit_device(n))
                btn_layout.addWidget(edit_btn)

                delete_btn = QPushButton()
                delete_btn.setIcon(QIcon.fromTheme("edit-delete"))
                delete_btn.setToolTip("Delete")
                delete_btn.setStyleSheet("border: none;")
                delete_btn.clicked.connect(lambda checked, n=name: self.delete_device(n))
                btn_layout.addWidget(delete_btn)

                self.table.setCellWidget(row, 3, btn_container)

            print_formatted(f"Table updated with {device_count} rows.", "debug")

        finally:
            self._refresh_lock = False

    # Opens device creation dialog to create new device
    def add_device(self):
        print_formatted("User clicked 'Add Device' button.", "info")
        dialog = AddDeviceDialog(self)

        print_formatted("Showing AddDeviceDialog...", "debug")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            print_formatted("AddDeviceDialog accepted.", "info")
            data = dialog.get_data()

            if data["name"] in self.devices:
                print_formatted(f"Duplicate device name: '{data['name']}' already exists.", "warning")
                QMessageBox.warning(self, "Duplicate", f"A device named '{data['name']}' already exists.")
                return

            self.devices[data["name"]] = {
                "sink_name": data["sink_name"],
                "description": data["description"],
                "slaves": data["slaves"]
            }

            print_formatted(f"Added device '{data['name']}' to internal list.", "info")

            print_formatted("Saving updated config to devices.json...", "debug")
            if save_devices_config(self.devices):
                print_formatted(f"Successfully saved device: {data['name']}", "success")
                self.last_sink_state = {}  # Forces a UI update and refreshes
                self.refresh_status()
            else:
                print_formatted(f"Failed to save device: {data['name']}", "error")
                QMessageBox.critical(self, "Save Failed", "Could not save the new device to config.")
        else:
            print_formatted("AddDeviceDialog cancelled by user.", "debug")

    # Opens device creation dialog to edit existing device
    def edit_device(self, device_name):
        print_formatted(f"Editing device: {device_name}", "info")
        info = self.devices[device_name]

        dialog = AddDeviceDialog(self)
        dialog.name_input.setText(device_name)
        dialog.sink_input.setText(info["sink_name"])
        dialog.desc_input.setText(info["description"])

        for i in range(dialog.sinks_list.count()):
            item = dialog.sinks_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) in info["slaves"]:
                item.setCheckState(Qt.CheckState.Checked)

        print_formatted("Showing AddDeviceDialog...", "debug")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            print_formatted("AddDeviceDialog accepted.", "info")
            data = dialog.get_data()

            if data["name"] in self.devices:
                print_formatted(f"Duplicate device name: '{data['name']}' already exists.", "warning")
                QMessageBox.warning(self, "Duplicate", f"A device named '{data['name']}' already exists.")
                return

            self.devices[data["name"]] = {
                "sink_name": data["sink_name"],
                "description": data["description"],
                "slaves": data["slaves"]
            }

            if device_name != data["name"]:
                del self.devices[device_name]

            print_formatted(f"Updated device: {data['name']}", "success")
            print_formatted("Saving updated config to devices.json...", "debug")
            if save_devices_config(self.devices):
                print_formatted(f"Successfully saved device: {data['name']}", "success")
                self.last_sink_state = {}
                self.refresh_status()
            else:
                print_formatted(f"Failed to save device: {data['name']}", "error")
                QMessageBox.critical(self, "Save Failed", "Could not save the updated device to config.")
        else:
            print_formatted("AddDeviceDialog cancelled by user.", "debug")

    # Opens delete confirmation prompt, if yes deletes and unloads device
    def delete_device(self, device_name):
        print_formatted(f"Deleting device: {device_name}", "warning")

        if device_name not in self.devices:
            print_formatted(f"Device '{device_name}' no longer exists.", "warning")
            QMessageBox.warning(self, "Not Found", f"Device '{device_name}' was not found.")
            return

        info = self.devices[device_name]

        reply = QMessageBox.question(
            self,
            "Delete Device",
            f"Are you sure you want to delete '{device_name}'?\nThis will also unload it if it's loaded.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.No:
            print_formatted("Deletion cancelled by user.", "debug")
            return

        # Unloads device before deleting
        # This could probably be handed off to unload_device()
        # TODO: Make unload_device() do this instead
        modules = self.get_all_modules()
        module_id = modules.get(info["sink_name"])
        if module_id:
            print_formatted(f"Unloading {device_name} before deletion...", "debug")
            cmd = ["pactl", "unload-module", f"{module_id}"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print_formatted(f"Unload failed: {result.stderr}", "error")
                QMessageBox.warning(self, "Unload Failed", f"Could not unload the device before deletion:\n{result.stderr}")
                return
            print_formatted(f"Unloaded {device_name} successfully", "success")

        del self.devices[device_name]

        print_formatted(f"Deleted device: {device_name}", "success")
        print_formatted("Saving updated config to devices.json...", "debug")
        if save_devices_config(self.devices):
            print_formatted("Successfully saved config after deletion.", "success")
            self.last_sink_state = {}
            self.refresh_status()
        else:
            print_formatted("Failed to save config after deletion.", "error")
            QMessageBox.critical(self, "Save Failed", "Could not save the config after deletion.")

    # Device loader
    def load_device(self, device_name):
        info = self.devices[device_name]
        sink_name = info["sink_name"]

        slaves_str = ",".join(info["slaves"])
        cmd = [
            "pactl", "load-module", "module-combine-sink",
            f"sink_name={sink_name}",
            f"sink_properties=device.description=\"{device_name}\"",
            f"slaves={slaves_str}"
        ]

        print_formatted(f"Constructed load command: {cmd}", "debug")

        print_formatted(f"Attempting to load device: {device_name} (sink_name={sink_name})", "info")
        modules = self.get_all_modules()
        if sink_name in modules:
            print_formatted(f"{device_name} is already loaded (ID: {modules[sink_name]})", "warning")
            self.refresh_status()
            return

        print_formatted(f"Running command: {cmd}", "DEBUG")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print_formatted(f"Loaded {device_name} successfully", "success")
            print_formatted(f"stdout: {result.stdout}", "debug")
            self.refresh_status()
        else:
            print_formatted(f"Load failed for {device_name}", "error")
            print_formatted(f"stderr: {result.stderr}", "debug")
            QMessageBox.warning(self, "Load Failed", f"Command failed:\n{result.stderr}")

    # Device unloader
    def unload_device(self, device_name):
        info = self.devices[device_name]
        sink_name = info["sink_name"]

        print_formatted(f"Attempting to unload device: {device_name} (sink_name={sink_name})", "info")
        modules = self.get_all_modules()
        module_id = modules.get(sink_name)

        if not module_id:
            print_formatted(f"{device_name} is not loaded.", "warning")
            self.refresh_status()
            return

        if not isinstance(module_id, str):
            print_formatted(f"module_id is not a string: {type(module_id)}", "error")
            return

        cmd = ["pactl", "unload-module", f"{module_id}"]
        print_formatted(f"Running command: {cmd}", "DEBUG")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            print_formatted(f"Unloaded {device_name} successfully", "success")
            print_formatted(f"stdout: {result.stdout}", "debug")
            self.refresh_status()
        else:
            print_formatted(f"Unload failed for {device_name}", "error")
            print_formatted(f"stderr: {result.stderr}", "debug")
            QMessageBox.warning(self, "Unload Failed", f"Command failed:\n{result.stderr}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PipeWireManager()
    window.show()
    sys.exit(app.exec())
