- check for self intersections at each step
- apply buffer(0) to all layers to 

- add and update are still unclear. test them and improve. do we need add? is it even active? Keep styling if layer exists
- Default line thickness shuld be: 0.13
- contour get a Label Label layer. Fix that
- counter labels have the text color per object, not form the layer color

# Caveats

## Linetype scale
linetypeScale sometimes does not stick. In Autocad you need to choose a different value and then go back to the original one.

## Linetype
When creating a dxf form scratch will be set but don't actually show up as such. You need in teh layer manager to load all line types one and they will then correctly show for all layers.

## Blunting
Right now we choose which angles to plant by giving a maximum angle. If we run into the issue that we blunt angles we do not want to blunt one ise is to create a point layer and we mark all the angles we want to blunt and we let the script blunt ionly angles that are around that point.