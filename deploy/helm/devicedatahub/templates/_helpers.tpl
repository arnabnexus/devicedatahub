{{- define "devicedatahub.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "devicedatahub.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name (include "devicedatahub.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "devicedatahub.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "devicedatahub.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
