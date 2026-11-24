import os
import pytest
from app.storage.local import StorageService
from app.analysis.profiling.profiler import DataProfiler

@pytest.mark.asyncio
async def test_storage_service(tmp_path):
    storage = StorageService(base_dir=str(tmp_path))
    data = b"id,name\n1,alpha\n2,beta"
    storage_key = await storage.save_file("test.csv", data)
    assert storage_key is not None
    
    # Read back
    read_data = storage.read_file(storage_key)
    assert read_data == data

    # Exists & Delete
    path = storage.get_file_path(storage_key)
    assert os.path.exists(path)
    assert storage.delete_file(storage_key) is True
    assert not os.path.exists(path)

def test_data_profiler_csv():
    sample_path = os.path.abspath("data/samples/incidents.csv")
    profile = DataProfiler.profile_file(sample_path, "incidents.csv")
    
    assert profile["row_count"] == 12
    assert profile["column_count"] == 6
    col_names = [c["name"] for c in profile["columns"]]
    assert "incident_id" in col_names
    assert "department" in col_names
    assert "severity" in col_names
    assert "resolution_hours" in col_names

    res_col = next(c for c in profile["columns"] if c["name"] == "resolution_hours")
    assert res_col["inferred_type"] in ["float", "integer"]
    assert res_col["null_count"] == 0
