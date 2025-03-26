# Adcanced Cookiecutter

This cog template is a more advanced version of the simple cog template. It includes a more robust structure for larger cogs, and utilizes Pydantic to objectify config data so that youre not messing around with dictionaries all the time.

## Key Components

- Subclassed commands, listeners, and tasks
- Pydantic "database" management
- Conservative i/o writes to disk
- Non blocking `self.save()` method
