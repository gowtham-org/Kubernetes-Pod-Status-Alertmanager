# Kubernetes Pod Status Alertmanager (CrashLoopBackOff) + Dashboard (Minikube)

This project deploys a Kubernetes monitor inside your cluster that:
- Detects Pods in **CrashLoopBackOff**
- Sends **Gmail alerts**
- Shows events in a simple **web dashboard**
- Exposes the dashboard publicly using **ngrok** (no domain / SSL setup needed)

Works on: **Windows + WSL2 Ubuntu**, **Minikube**.

## Prerequisites:
1. Minikube
2. Sops
3. Kubectl
4. ngrok
5. helm

---

## Prerequisites (one-time)

### 1) Install and start Minikube
You should already have Minikube installed.

Start the cluster:
```bash
minikube start
Create
Update .sops.yaml with the  gmail details, gamil password, ngrok auth token
Create values-Secrets.yaml and encrypt them using SOPS key
Update the sops key in .sops.yaml and encrypt the files using 
sops -e values-secrets.yaml > values-secrets.enc.yaml
Dont push values-secrets.yaml to github

python -m venv venv

source venv/bin/activate

kubectl get ns monitoring || kubectl create ns monitoring
helm secrets upgrade --install crashloop ./charts/crashloop-stack \
  -n monitoring \
  -f ./charts/crashloop-stack/values.yaml \
  -f ./values-secrets.enc.yaml

kubectl apply -f crashloop-stack/crashloop-test.yaml

sudo snap install ngrok

ngrok version

kubectl get pods -n monitoring

kubectl describe pod <pod-name> -n monitoring

###Run below command:
kubectl -n monitoring port-forward pod/crashloop-7678978bb-7klwr 4040:4040
### Keep this terminal running
###In a new terminal, fetch the public ngrok URL 
curl -s http://127.0.0.1:4040/api/tunnels | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["tunnels"][0]["public_url"])'
That prints something like:
https://xxxxx.ngrok-free.dev


Final URL for Demo:
https://dimple-unaisled-sharilyn.ngrok-free.dev/