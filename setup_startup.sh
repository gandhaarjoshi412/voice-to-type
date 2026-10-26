#!/bin/bash

# Ensure this is run with sudo
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script with sudo: sudo ./setup_startup.sh"
  exit 1
fi

echo "1. Setting up ydotoold as a background system service..."
cat << 'EOF' > /etc/systemd/system/ydotoold.service
[Unit]
Description=ydotool daemon (Public Socket)
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/ydotoold -p /tmp/.ydotool_socket -P 0666
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ydotoold.service
systemctl start ydotoold.service
echo "ydotoold system service enabled and started!"

echo "2. Setting up Voice-to-Type app to run automatically on login..."
USER_HOME=$(eval echo ~${SUDO_USER})
mkdir -p $USER_HOME/.config/autostart

cat << 'EOF' > $USER_HOME/.config/autostart/voice-to-type.desktop
[Desktop Entry]
Type=Application
Name=Voice To Type Service
Comment=Background voice-to-text service with system tray and analytics
Exec=/home/gandhaar/project/projects/voice_to_type_project/run_app.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=2
Terminal=false
EOF

chown ${SUDO_USER}:${SUDO_USER} $USER_HOME/.config/autostart/voice-to-type.desktop
echo "Autostart entry created!"

echo ""
echo "============================================="
echo "Setup is completely finished!"
echo "From now on, whenever you boot up your laptop:"
echo "  - The ydotool daemon will start silently in the background."
echo "  - The Voice to Type app will automatically launch."
echo "============================================="
