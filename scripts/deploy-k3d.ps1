param(
    [string]$ClusterName = "trophy-local",
    [string]$Namespace = "execution-zone",
    [string]$ReleaseName = "dewey",
    [string]$ImageRepository = "dewey-execution",
    [string]$ImageTag = "latest"
)

$ErrorActionPreference = "Stop"

function Assert-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

Assert-Command -Name "docker"
Assert-Command -Name "k3d"
Assert-Command -Name "kubectl"
Assert-Command -Name "helm"

Write-Host "[1/6] Ensuring k3d cluster '$ClusterName' exists..."
$clusterExists = k3d cluster list | Select-String -SimpleMatch $ClusterName
if (-not $clusterExists) {
    k3d cluster create $ClusterName --agents 1
}

Write-Host "[2/6] Building image $ImageRepository`:$ImageTag..."
docker build -t "$ImageRepository`:$ImageTag" .

Write-Host "[3/6] Importing image into k3d cluster '$ClusterName'..."
k3d image import "$ImageRepository`:$ImageTag" -c $ClusterName

Write-Host "[4/6] Ensuring namespace '$Namespace' exists..."
kubectl get namespace $Namespace 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
    kubectl create namespace $Namespace | Out-Null
}

Write-Host "[5/6] Applying Dewey Helm release '$ReleaseName'..."
helm upgrade --install $ReleaseName ./charts/dewey `
    --namespace $Namespace `
    --create-namespace `
    --set image.repository=$ImageRepository `
    --set image.tag=$ImageTag

Write-Host "[6/6] Current rollout status..."
kubectl rollout status deployment/$ReleaseName-dewey -n $Namespace --timeout=120s
kubectl get pods,svc -n $Namespace

Write-Host "Deployment complete: release '$ReleaseName' in namespace '$Namespace'."
