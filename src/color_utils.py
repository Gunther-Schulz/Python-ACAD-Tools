import random

def get_color_code(color, name_to_aci):
    if isinstance(color, int):
        if 1 <= color <= 255:
            return color
        else:
            random_color = random.randint(1, 255)
            print(f"Warning: Invalid color code {color}. Assigning random color: {random_color}")
            return random_color
    elif isinstance(color, str):
        color_lower = color.lower()
        if color_lower in name_to_aci:
            return name_to_aci[color_lower]
        else:
            random_color = random.randint(1, 255)
            print(f"Warning: Color name '{color}' not found. Assigning random color: {random_color}")
            return random_color
    else:
        random_color = random.randint(1, 255)
        print(f"Warning: Invalid color type. Assigning random color: {random_color}")
        return random_color