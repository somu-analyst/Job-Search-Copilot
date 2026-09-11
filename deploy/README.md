# Deploying to the Oracle VM (`nyse-bot` @ 150.136.41.250)

Own directory, own venv, own systemd units, own port (8503) -- kept fully separate from the
NYSE trading bot that also lives on this box, which is the only thing this VM's Always Free
allowance is actually meant for. It shares CPU/RAM, nothing else.

## 1. Bootstrap (one time, or to pick up code updates)

`deploy/` isn't committed to GitHub yet, so the very first time, clone first into an empty
directory, then layer the deploy files on top of that clone (in that order -- `git clone`
refuses a non-empty target):

```
ssh -i ~/oci-nyse.key ubuntu@150.136.41.250 "git clone https://github.com/somu-analyst/Job-Search-Copilot.git /home/ubuntu/job-search-copilot"
scp -i ~/oci-nyse.key -r deploy ubuntu@150.136.41.250:/home/ubuntu/job-search-copilot/
ssh -i ~/oci-nyse.key ubuntu@150.136.41.250 "bash /home/ubuntu/job-search-copilot/deploy/setup_vm.sh"
```

Once `deploy/` is committed and pushed to the repo, later runs are simpler -- just
`ssh ... "cd /home/ubuntu/job-search-copilot && git pull && bash deploy/setup_vm.sh"`, since a
plain `git pull` (not a fresh clone) picks up the deploy files along with everything else.

At this point the scan timer and dashboard are both running against the **demo** dataset
(`config/profile.demo.yml` + `resume/cv.demo.md` + `data/demo_jobs.db`) -- same graceful
fallback a fresh local clone gets. Nothing personal has left this machine yet.

## 2. Push your real config (one time; contains your resume, contact info, and API keys)

None of this is auto-generated -- these are your secrets. From this repo locally:

```
scp -i ~/oci-nyse.key config/profile.yml ubuntu@150.136.41.250:/home/ubuntu/job-search-copilot/config/profile.yml
scp -i ~/oci-nyse.key resume/cv.md ubuntu@150.136.41.250:/home/ubuntu/job-search-copilot/resume/cv.md
# only if you use it:
scp -i ~/oci-nyse.key resume/article-digest.md ubuntu@150.136.41.250:/home/ubuntu/job-search-copilot/resume/article-digest.md
```

`src/ai.py` reads the OpenRouter key from a `.env` next to a "career-ops dir" (your local
machine already has this at `career-ops/career-ops/.env`) -- rather than copy that whole
project, create a minimal stand-in on the VM with just the one line:

```
ssh -i ~/oci-nyse.key ubuntu@150.136.41.250 "mkdir -p /home/ubuntu/career-ops-min"
echo "OPENROUTER_API_KEY=<your key>" | ssh -i ~/oci-nyse.key ubuntu@150.136.41.250 "cat > /home/ubuntu/career-ops-min/.env"
```

Then add this to the VM's `config/profile.yml` under `resume:` so it's found:

```yaml
resume:
  careerops_dir: "/home/ubuntu/career-ops-min"
```

## 3. Restart to pick up the real config

```
ssh -i ~/oci-nyse.key ubuntu@150.136.41.250 "sudo systemctl restart jobscout-dashboard.service"
```

(`jobscout-scan.timer` picks up config changes on its next scheduled fire automatically --
no restart needed, it's a oneshot service, not a long-running process.)

## Viewing the dashboard

No public port -- same reasoning as `nyse-dashboard`: this app has no login of its own and the
jobs table carries your application-status history.

```
ssh -i ~/oci-nyse.key -L 8503:127.0.0.1:8503 ubuntu@150.136.41.250
```

then open `http://localhost:8503` locally.

## Operating

```
systemctl status jobscout-scan.timer jobscout-dashboard.service
journalctl -u jobscout-scan -n 100          # last scan's output
sudo systemctl start jobscout-scan.service  # trigger a scan right now, don't wait for the timer
```
