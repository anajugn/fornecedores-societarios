terraform {
  required_version = ">= 1.5"
  required_providers {
    aiven = {
      source  = "aiven/aiven"
      version = ">= 4.0.0, < 5.0.0"
    }
  }
}

provider "aiven" {
  api_token = var.aiven_api_token
}

resource "aiven_pg" "pg" {
  project      = var.project_name
  plan         = var.plan
  service_name = var.service_name
  cloud_name   = var.cloud_name   # null = o Aiven escolhe; no free ele costuma definir sozinho
}