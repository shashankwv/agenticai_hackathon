
def transform_batch(raw_records: list) -> list:
    cleansed_records = []
    for record in raw_records:
        if isinstance(record, dict):
            cleansed_records.append(dict(record))
    return cleansed_records
