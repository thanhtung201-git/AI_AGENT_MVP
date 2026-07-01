from abc import ABC, abstractmethod
from typing import Any, Dict, Type

class BaseTool(ABC):
    """Base class for all AI Agent tools."""
    
    name: str = ""
    description: str = ""
    
    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with given arguments."""
        pass
        
    @property
    def input_schema(self) -> Dict[str, Any]:
        """Return JSON schema of expected inputs."""
        return {}
        
    @property
    def output_schema(self) -> Dict[str, Any]:
        """Return JSON schema of expected outputs."""
        return {}
