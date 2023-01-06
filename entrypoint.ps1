<#
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateNotNullOrEmpty()]
    [string]$Profile
)

$ErrorActionPreference = "Stop"
. ./ps-cibootstrap/bootstrap.ps1

########
# Capture version information
$version = @($Env:GITHUB_REF, "v0.1.0") | Select-ValidVersions -First -Required

Write-Information "Version:"
$version

$dockerImageName = "archmachina/helm-elasticlog"

########
# Build stage
Invoke-CIProfile -Name $Profile -Steps @{

    lint = @{
        Steps = {
            Write-Information "Linting chart"
            Invoke-Native { helm lint source/elasticlog }
        }
    }

    build = @{
        Steps = {
            Write-Information "Package directory"
            Use-BuildDirectory packages

            Write-Information "Package helm chart"
            Invoke-Native { helm package source/elasticlog -d packages/ --app-version $version.PlainVersion --version $version.PlainVersion }
        }
    }

    pr = @{
        Steps = "build"
    }

    latest = @{
        Steps = "build"
    }

    release = @{
        Steps = "build", {
            $owner = "archmachina"
            $repo = "helm-elasticlog"

            $releaseParams = @{
                Owner = $owner
                Repo = $repo
                Name = ("Release " + $version.Tag)
                TagName = $version.Tag
                Draft = $false
                Prerelease = $version.IsPrerelease
                Token = $Env:GITHUB_TOKEN
            }

            Write-Information "Creating release"
            New-GithubRelease @releaseParams

            # Attempt login to docker registry
            Write-Information "Attempting login for docker registry"
            Invoke-Native -Script { $Env:DOCKER_HUB_TOKEN | docker login --password-stdin -u archmachina docker.io }

            Invoke-Native { helm push ("packages/elasticlog-{0}.tgz" -f $version.PlainVersion) oci://registry-1.docker.io/archmachina }
        }
    }
}
