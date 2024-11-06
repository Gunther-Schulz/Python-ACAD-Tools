- Layer order
- relative positioning for paperspace items to each other
- get center of a layer to iuse to setthe viewport model view center
- intelligent placemez for flurstücke (might be hard and/or not worth it). Is there a library for that?
- generate better geometry for flur/gematrkung/gemeinde that doesnt overlay each other (hard one)
- cut rectangles from vp corners (tried, couldmt get it to work. docs lacking)



- Default line thickness shuld be: 0.13
- contour get a Label Label layer. Fix that
- countour labels have the text color per object, not form the layer color

# Caveats

## Linetype scale
linetypeScale sometimes does not stick. In Autocad you need to choose a different value and then go back to the original one.

## Linetype
When creating a dxf form scratch will be set but don't actually show up as such. You need in teh layer manager to load all line types one and they will then correctly show for all layers.

## Scale
Hatch pattern scales can sometimes look differnt of the script sets it or if we choose the exact same value in autocad. unclear why. so far we have noticed that with legend items. man map geometry seems to hatch fine.

## Blunting - depracted for now, too complex
Right now we choose which angles to plant by giving a maximum angle. If we run into the issue that we blunt angles we do not want to blunt one ise is to create a point layer and we mark all the angles we want to blunt and we let the script blunt ionly angles that are around that point.


## Merge should really be dissolve