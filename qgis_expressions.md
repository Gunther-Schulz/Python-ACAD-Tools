# Bäume
```
concat(
    CASE WHEN "Art" != 0 THEN concat('Art: ', "Art", '\n') ELSE '' END,
    CASE WHEN "Krone_D" != 0 THEN concat('Krone D: ', "Krone_D", ' m\n') ELSE '' END,
    CASE WHEN "Stamm_D" != 0 THEN concat('Stamm D: ', "Stamm_D", ' m\n') ELSE '' END,
    CASE WHEN "Höhe" != 0 THEN concat('Höhe: ', "Höhe", ' m\n') ELSE '' END
)
```

