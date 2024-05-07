python -m reckon kubernetes simple_k8s none -d --system_logs /results/logs
python -m reckon kubernetes simple_k8s leader-recovery --create-ratio=0 --read-ratio=1 --update-ratio=0 --delete-ratio=0