output "host" {
  value = aiven_pg.pg.service_host
}

output "port" {
  value = aiven_pg.pg.service_port
}

output "database" {
  value = "defaultdb"
}

output "service_uri" {
  value     = aiven_pg.pg.service_uri
  sensitive = true
}