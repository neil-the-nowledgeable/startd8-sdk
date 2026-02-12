"""
Tests for API key encryption and export/import functionality
"""

import pytest
import tempfile
from pathlib import Path

pytest.importorskip("cryptography", reason="cryptography package required for encryption tests")

from startd8.security import KeyEncryption, store_encrypted_keys, load_encrypted_keys
from startd8.exceptions import ConfigurationError


class TestKeyEncryption:
    """Test encryption and decryption of API keys"""
    
    def test_encrypt_decrypt_data(self):
        """Test basic encryption and decryption"""
        encryptor = KeyEncryption()
        
        data = {'test': 'value', 'number': 42}
        password = 'test_password_12345'
        
        # Encrypt
        encrypted = encryptor.encrypt_data(data, password)
        assert isinstance(encrypted, str)
        assert len(encrypted) > 0
        
        # Decrypt
        decrypted = encryptor.decrypt_data(encrypted, password)
        assert decrypted == data
    
    def test_encrypt_decrypt_api_keys(self):
        """Test API key encryption with metadata"""
        encryptor = KeyEncryption()
        
        api_keys = {
            'ANTHROPIC_API_KEY': 'sk-ant-test123',
            'OPENAI_API_KEY': 'sk-proj-test456'
        }
        metadata = {'source': 'test', 'version': '1.0'}
        password = 'strong_password_789'
        
        # Encrypt
        encrypted = encryptor.encrypt_api_keys(api_keys, password, metadata)
        assert isinstance(encrypted, str)
        
        # Decrypt
        package = encryptor.decrypt_api_keys(encrypted, password)
        assert 'api_keys' in package
        assert 'metadata' in package
        assert package['api_keys'] == api_keys
        assert package['metadata']['source'] == 'test'
    
    def test_wrong_password_fails(self):
        """Test that wrong password fails decryption"""
        encryptor = KeyEncryption()
        
        data = {'secret': 'value'}
        password = 'correct_password'
        wrong_password = 'wrong_password'
        
        encrypted = encryptor.encrypt_data(data, password)
        
        with pytest.raises(ConfigurationError, match="incorrect password"):
            encryptor.decrypt_data(encrypted, wrong_password)
    
    def test_invalid_data_fails(self):
        """Test that invalid encrypted data fails"""
        encryptor = KeyEncryption()
        
        with pytest.raises(ConfigurationError):
            encryptor.decrypt_data("invalid_data", "password")
    
    def test_different_passwords_produce_different_outputs(self):
        """Test that same data with different passwords produces different outputs"""
        encryptor = KeyEncryption()
        
        data = {'key': 'value'}
        password1 = 'password1'
        password2 = 'password2'
        
        encrypted1 = encryptor.encrypt_data(data, password1)
        encrypted2 = encryptor.encrypt_data(data, password2)
        
        # Different passwords should produce different encrypted data
        assert encrypted1 != encrypted2
        
        # But both should decrypt correctly with their own passwords
        assert encryptor.decrypt_data(encrypted1, password1) == data
        assert encryptor.decrypt_data(encrypted2, password2) == data
    
    def test_store_and_load_encrypted_keys(self):
        """Test storing and loading encrypted keys to/from file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test_keys.enc"
            
            api_keys = {
                'ANTHROPIC_API_KEY': 'sk-ant-test',
                'OPENAI_API_KEY': 'sk-test'
            }
            password = 'file_password_123'
            
            # Store
            store_encrypted_keys(file_path, api_keys, password)
            assert file_path.exists()
            
            # Load
            loaded_keys = load_encrypted_keys(file_path, password)
            assert loaded_keys == api_keys
    
    def test_load_nonexistent_file_fails(self):
        """Test that loading non-existent file fails"""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nonexistent.enc"
            
            with pytest.raises(FileNotFoundError):
                load_encrypted_keys(file_path, "password")
    
    def test_password_strength_requirements(self):
        """Test that weak passwords are handled appropriately"""
        encryptor = KeyEncryption()
        
        data = {'test': 'data'}
        
        # Very short password should still work (enforced in TUI, not in library)
        weak_password = '123'
        encrypted = encryptor.encrypt_data(data, weak_password)
        decrypted = encryptor.decrypt_data(encrypted, weak_password)
        assert decrypted == data
    
    def test_large_data_encryption(self):
        """Test encryption of large data sets"""
        encryptor = KeyEncryption()
        
        # Create large API key dictionary
        large_data = {f'API_KEY_{i}': f'sk-test-{i}' * 100 for i in range(100)}
        password = 'large_data_password'
        
        encrypted = encryptor.encrypt_data(large_data, password)
        decrypted = encryptor.decrypt_data(encrypted, password)
        
        assert decrypted == large_data
    
    def test_special_characters_in_password(self):
        """Test that passwords with special characters work"""
        encryptor = KeyEncryption()
        
        data = {'key': 'value'}
        special_password = 'P@ssw0rd!#$%^&*()_+-=[]{}|;:,.<>?'
        
        encrypted = encryptor.encrypt_data(data, special_password)
        decrypted = encryptor.decrypt_data(encrypted, special_password)
        
        assert decrypted == data
    
    def test_unicode_in_data(self):
        """Test that Unicode characters in data are handled correctly"""
        encryptor = KeyEncryption()
        
        data = {
            'key': 'value',
            'unicode': '你好世界',
            'emoji': '🔐🔑✅'
        }
        password = 'unicode_test'
        
        encrypted = encryptor.encrypt_data(data, password)
        decrypted = encryptor.decrypt_data(encrypted, password)
        
        assert decrypted == data

