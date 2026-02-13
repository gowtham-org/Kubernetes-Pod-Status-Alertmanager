# Kubernetes Pod Status Alertmanager (CrashLoopBackOff) + Dashboard (Minikube)

This project deploys a Kubernetes monitor inside your cluster that:
- Detects Pods in **CrashLoopBackOff**
- Sends **Gmail alerts**
- Shows events in a simple **web dashboard**
- Exposes the dashboard publicly using **ngrok** (no domain / SSL setup needed)

Works on: **Windows + WSL2 Ubuntu**, **Minikube**.

---

## Prerequisites (one-time)

### 1) Install and start Minikube
You should already have Minikube installed.

Start the cluster:
```bash
minikube start


Final URL for Demo:
https://dimple-unaisled-sharilyn.ngrok-free.dev/