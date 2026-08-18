{{- define "software-factory.name" -}}
software-factory
{{- end -}}

{{- define "software-factory.labels" -}}
app.kubernetes.io/name: software-factory
app.kubernetes.io/managed-by: Helm
softwarefactory.io/tenant: {{ .Values.tenant.name | quote }}
softwarefactory.io/environment: {{ .Values.tenant.environment | quote }}
{{- end -}}
