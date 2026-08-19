{{- define "software-factory.name" -}}
software-factory
{{- end -}}

{{- define "software-factory.labels" -}}
app.kubernetes.io/name: software-factory
app.kubernetes.io/managed-by: Helm
softwarefactory.io/tenant: {{ .Values.tenant.name | quote }}
softwarefactory.io/environment: {{ .Values.tenant.environment | quote }}
{{- end -}}

{{- /*
Labels for a single component of the tenant factory. Call with a dict that
carries the root context and the component name, e.g.

  {{ include "software-factory.componentLabels" (dict "ctx" $ "name" "pocket-id") }}
*/ -}}
{{- define "software-factory.componentLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/part-of: software-factory
app.kubernetes.io/managed-by: Helm
softwarefactory.io/tenant: {{ .ctx.Values.tenant.name | quote }}
softwarefactory.io/environment: {{ .ctx.Values.tenant.environment | quote }}
{{- end -}}

{{- /* Cluster-internal base URL of Pocket ID, used by workloads in the same namespace. */ -}}
{{- define "software-factory.pocketIdInternalUrl" -}}
http://pocket-id.{{ .Values.tenant.namespace }}.svc.cluster.local:{{ .Values.identity.pocketId.service.port }}
{{- end -}}

{{- /* Name of the secret holding the Pocket ID encryption key and static API key. */ -}}
{{- define "software-factory.pocketIdSecretName" -}}
{{- if .Values.identity.pocketId.existingSecret -}}
{{ .Values.identity.pocketId.existingSecret }}
{{- else -}}
pocket-id
{{- end -}}
{{- end -}}

{{- /* Name of the secret holding the OIDC client secret of the group explorer test app. */ -}}
{{- define "software-factory.groupExplorerSecretName" -}}
{{- if .Values.groupExplorer.existingSecret -}}
{{ .Values.groupExplorer.existingSecret }}
{{- else -}}
group-explorer-oidc
{{- end -}}
{{- end -}}

{{- /* Browser-facing redirect URI of the group explorer test app. */ -}}
{{- define "software-factory.groupExplorerRedirectUri" -}}
{{ trimSuffix "/" .Values.groupExplorer.publicUrl }}/callback
{{- end -}}
