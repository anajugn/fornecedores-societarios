variable "aiven_api_token" {
  type      = string
  sensitive = true
  # sem default: use  $env:TF_VAR_aiven_api_token = "..."
}

variable "project_name" {
  type = string
}

variable "plan" {
  type    = string
  default = "free-1-1gb"
}

variable "service_name" {
  type    = string
  default = "pg-fornecedores"
}

variable "cloud_name" {
  type    = string
  default = null   # só preencha se o terraform plan reclamar
}