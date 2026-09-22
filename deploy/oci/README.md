# Zero monthly cost deployment on OCI Always Free

These files prepare a **single** Ubuntu VM deployment. They do not create cloud resources or guarantee uninterrupted service. OCI can reclaim an idle Always Free VM, and capacity may be unavailable. The project keeps SQLite and uploads on the VM's persistent boot volume; keep separate backups. Stay within the Always Free compute, boot-volume, backup, and network allowances. Do not upgrade to paid resources unless you intend to pay.

## 1. Create the VM and hostname

Create an Oracle Cloud account and an **Always Free** Ubuntu VM in your home region. An Ampere A1 VM with 1 OCPU and 6 GB RAM fits within the Always Free allocation when you have no other A1 usage. The AMD E2 micro is another option if A1 capacity is unavailable. Keep the default 50 GB boot volume within the free 200 GB total. Allow inbound TCP 22 only from your IP, plus 80 and 443 publicly in the OCI security list and the VM firewall. Do not expose port 8000. Save the SSH key securely.

Create a free DuckDNS subdomain and point it at the VM's public IPv4 address. This gives you a hostname that you can point to a replacement VM if its IP changes. Verify DNS resolves to the VM before configuring HTTPS. Set up OCI's boot-volume backup policy and verify it creates backups within the five included Always Free backup slots.

## 2. Install code and dependencies

Copy the **code only** to `/srv/lost-found` (for example with Git or `rsync`); do not include a local `.venv`, `.env`, or SQLite file in a public repository. On the VM:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
sudo mkdir -p /srv/lost-found /var/lib/lost-found
sudo chown -R ubuntu:ubuntu /srv/lost-found /var/lib/lost-found
cd /srv/lost-found
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

If you have existing local reports, use the data archive described below to move the SQLite database and photos to `/var/lib/lost-found` **before the first application start**. Because restore refuses to overwrite a directory, remove the newly created empty directory with `sudo rmdir /var/lib/lost-found` and run restore with `sudo`, then run `sudo chown -R ubuntu:ubuntu /var/lib/lost-found`. An empty deployment can start with that directory empty.

## 3. Configure the app service and HTTPS

Copy `lost-found.env.example` to `/etc/lost-found.env`. Replace the secret and hostname. Keep `APP_DATA_DIR=/var/lib/lost-found` and `APP_COOKIE_SECURE=1`. The secret must remain the same across restarts and upgrades. Restrict the file:

```bash
sudo chown root:ubuntu /etc/lost-found.env
sudo chmod 640 /etc/lost-found.env
```

Copy `lost-found.service.example` to `/etc/systemd/system/lost-found.service`. This runs one Gunicorn worker for SQLite and restarts it after a failure. Start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lost-found
sudo systemctl status lost-found
```

Install Caddy using its [official Linux instructions](https://caddyserver.com/docs/install). Copy `Caddyfile.example` to `/etc/caddy/Caddyfile`, replace the hostname, then run:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl reload caddy
```

Caddy obtains and renews HTTPS certificates when DNS points to the VM and ports 80/443 are reachable. Open the HTTPS URL from a different device, test signup, report creation, photo display, and a restart. Only share the link after these checks pass.

## 4. Keep data recoverable

The application stores both `lost_and_found.sqlite` and `uploads/` in `/var/lib/lost-found`. An app code update must never replace or delete that directory. Before each update, stop the app, make a consistent archive, then restart it:

```bash
sudo systemctl stop lost-found
cd /srv/lost-found
.venv/bin/python -m scripts.data_archive backup --data-dir /var/lib/lost-found --archive /home/ubuntu/lost-found-backup.tar.gz
sudo systemctl start lost-found
```

Copy the archive **off the VM** to a private location, such as an OCI Object Storage bucket within its Always Free allowance or your own computer. Keep more than one dated archive and regularly test a restore. The archive contains user data and photos, so keep it private. The boot-volume backup policy is a second recovery path, not a replacement for the app-data archive.

To restore on a new VM, install the code and dependencies, place the archive there, and restore **before starting** the service. The restore command refuses to overwrite an existing data directory. If setup created an empty directory, remove it with `rmdir` first; it will refuse if the directory contains data:

```bash
cd /srv/lost-found
sudo rmdir /var/lib/lost-found
sudo .venv/bin/python -m scripts.data_archive restore --archive /home/ubuntu/lost-found-backup.tar.gz --data-dir /var/lib/lost-found
sudo chown -R ubuntu:ubuntu /var/lib/lost-found
```

Keep the original `SECRET_KEY` separately from the archive to preserve existing sessions. If the old VM was lost, update DuckDNS to the new VM's IP and start the services. A backup only preserves data through its creation time; take one immediately before planned changes and on a regular schedule.

## Sources and limits

- [OCI Always Free compute, storage, and idle reclamation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [OCI boot-volume backups](https://docs.oracle.com/en-us/iaas/Content/Block/Tasks/create-bv-boot-volume-backup.htm)
- [DuckDNS free hostname](https://www.duckdns.org/about.jsp)
- [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https)
