select * from telemetry;

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'telemetry'
ORDER BY ordinal_position;

select * from telemetry order   by timestamp desc;