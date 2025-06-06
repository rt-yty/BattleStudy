from dataclasses import dataclass

@dataclass
class Player:
    user_id: int
    username: str = None
    first_name: str = None
    rating: int = 0 
    preferred_level: str = None
    
    @property
    def display_name(self) -> str:
        if self.username:
            return f"@{self.username}"
        return self.first_name or f"User {self.user_id}"